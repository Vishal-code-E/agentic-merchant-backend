"""Turns a shopper's free-text chat message into a CheckoutRequest, using an LLM
constrained to the merchant's real catalog. Feeds /agent/chat-checkout; checkout_graph
itself is untouched — this module only ever produces its input."""
import json
import uuid

import anthropic
import openai
from pydantic import ValidationError

from app.config.settings import get_settings
from app.models.product import Product
from app.schemas.checkout import CheckoutCartItem, CheckoutRequest

#: One-shot extraction call, not an agentic loop — no model-selection knob
#: beyond model_provider.
ANTHROPIC_MODEL_ID = "claude-opus-5"
OPENAI_MODEL_ID = "gpt-4o-mini"

#: Raised for a configuration problem (missing key, unsupported provider) —
#: distinct from ValueError/KeyError below, which mean "the model answered
#: but we couldn't trust the answer." Callers map this to a 503, not a 500.
class IntentParserUnavailable(RuntimeError):
    pass


_SYSTEM_PROMPT = (
    "You are a shopping cart interpreter for an e-commerce merchant. Given a "
    "shopper's natural-language message and the merchant's live product catalog "
    "(JSON: id, name, price, category), decide which catalog products and "
    "quantities satisfy the request.\n"
    "- Only ever use product ids that appear in the catalog; never invent one.\n"
    "- If the message doesn't map to any confident, in-catalog purchase (asks "
    "for something not sold, is too vague, or is nonsensical for this store), "
    "set matched=false, leave cart_items empty, and give a one-line reason in "
    "explanation.\n"
    "- If it matches, set matched=true, fill cart_items, and write explanation "
    "as one line starting with 'Interpreted as: ', naming the products/"
    "quantities chosen and, when a budget or 'cheapest' constraint was given, "
    "the specific product and price picked to satisfy it.\n"
    "- When a budget or 'cheapest' constraint is given, prefer the cheapest "
    "in-catalog product that satisfies the other constraints."
)


def _build_schema(catalog_ids: list[str]) -> dict:
    """product_id is enum-constrained to the caller's own catalog ids — the model
    is structurally unable to hallucinate a product_id, not just asked nicely not to."""
    return {
        "type": "object",
        "properties": {
            "matched": {"type": "boolean"},
            "cart_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "product_id": {"type": "string", "enum": catalog_ids},
                        "quantity": {"type": "integer", "minimum": 1},
                    },
                    "required": ["product_id", "quantity"],
                    "additionalProperties": False,
                },
            },
            "explanation": {"type": "string"},
        },
        "required": ["matched", "cart_items", "explanation"],
        "additionalProperties": False,
    }


def _catalog_context(catalog: list[Product]) -> list[dict]:
    return [
        {"id": str(p.id), "name": p.name, "price": float(p.price), "category": p.category}
        for p in catalog
    ]


def _user_content(catalog_context: list[dict], user_message: str) -> str:
    return f"Catalog:\n{json.dumps(catalog_context)}\n\nShopper message: {user_message!r}"


async def _call_anthropic(catalog_context: list[dict], catalog_ids: list[str], user_message: str, api_key: str):
    """Returns (parsed_dict, None) or (None, explanation) on a clean model-side failure."""
    if not api_key:
        raise IntentParserUnavailable("ANTHROPIC_API_KEY is not set; chat-checkout is unavailable.")

    client = anthropic.AsyncAnthropic(api_key=api_key)
    response = await client.messages.create(
        model=ANTHROPIC_MODEL_ID,
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _user_content(catalog_context, user_message)}],
        # effort=low: this is plain classification/extraction, not agentic work.
        output_config={"format": {"type": "json_schema", "schema": _build_schema(catalog_ids)}, "effort": "low"},
    )

    if response.stop_reason == "max_tokens":
        return None, "Could not interpret the request (response truncated)."

    text_block = next((b for b in response.content if b.type == "text"), None)
    if text_block is None:
        return None, "Could not interpret the request (no structured response from the model)."

    return json.loads(text_block.text), None


async def _call_openai(catalog_context: list[dict], catalog_ids: list[str], user_message: str, api_key: str):
    if not api_key:
        raise IntentParserUnavailable("OPENAI_API_KEY is not set; chat-checkout is unavailable.")

    client = openai.AsyncOpenAI(api_key=api_key)
    response = await client.chat.completions.create(
        model=OPENAI_MODEL_ID,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": _user_content(catalog_context, user_message)},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {"name": "cart_interpretation", "strict": True, "schema": _build_schema(catalog_ids)},
        },
    )

    choice = response.choices[0]
    if choice.finish_reason == "length":
        return None, "Could not interpret the request (response truncated)."

    content = choice.message.content
    if not content:
        return None, "Could not interpret the request (no structured response from the model)."

    return json.loads(content), None


async def parse_intent_to_cart(
    user_message: str, catalog: list[Product], merchant_id: str
) -> tuple[CheckoutRequest | None, str]:
    """
    Returns (CheckoutRequest, explanation) on a confident match, or
    (None, explanation) otherwise — never forces an empty/best-guess cart
    through to checkout_graph. Raises IntentParserUnavailable for a
    configuration problem (missing key, unsupported provider) — the router
    maps that to a 503, distinct from a normal "no match" 200.
    """
    settings = get_settings()

    if not catalog:
        return None, "Merchant has no products in stock; nothing to interpret against."

    catalog_context = _catalog_context(catalog)
    catalog_ids = [item["id"] for item in catalog_context]

    if settings.model_provider == "anthropic":
        parsed, early_explanation = await _call_anthropic(
            catalog_context, catalog_ids, user_message, settings.anthropic_api_key
        )
    elif settings.model_provider == "openai":
        parsed, early_explanation = await _call_openai(
            catalog_context, catalog_ids, user_message, settings.openai_api_key
        )
    else:
        raise IntentParserUnavailable(
            f"model_provider={settings.model_provider!r} has no intent-parsing implementation yet."
        )

    if early_explanation is not None:
        return None, early_explanation

    if not parsed.get("matched") or not parsed.get("cart_items"):
        return None, parsed.get("explanation") or "Could not confidently match this request to a product."

    try:
        cart_request = CheckoutRequest(
            merchant_id=uuid.UUID(merchant_id),
            cart_items=[
                CheckoutCartItem(product_id=uuid.UUID(item["product_id"]), quantity=item["quantity"])
                for item in parsed["cart_items"]
            ],
        )
    except (ValidationError, ValueError, KeyError) as e:
        return None, f"Model returned an invalid cart ({e}); refusing to guess."

    return cart_request, parsed.get("explanation") or "Interpreted as a valid cart."
