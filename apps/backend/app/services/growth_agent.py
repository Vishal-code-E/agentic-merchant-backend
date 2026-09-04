"""Reasons over campaign_graph's SegmentCustomers output to recommend marketing
actions, using the same Anthropic/OpenAI structured-output pattern as
intent_parser.py. Feeds campaign_graph.py's recommend_actions_node; that graph
is otherwise untouched — this module only ever produces its input."""
import json
import logging

import anthropic
import openai
from pydantic import BaseModel, Field

from app.config.settings import get_settings
from app.models.merchant import Merchant
from app.models.policy import Policy
from app.models.product import Product
from app.services.intent_parser import ANTHROPIC_MODEL_ID, OPENAI_MODEL_ID

logger = logging.getLogger(__name__)


class GrowthAgentUnavailable(RuntimeError):
    """Configuration problem (missing key, unsupported provider) — caught internally, never raised to callers."""


class CampaignAction(BaseModel):
    action: str
    target_segment: str
    reasoning: str
    #: Range-constrained here too (not just in the JSON schema below) — belt and suspenders,
    #: same principle as the cart product_id enum in intent_parser.py.
    suggested_discount_pct: float | None = Field(default=None, ge=0, le=30)
    confidence: float = Field(ge=0, le=1)
    path: str  # "llm_reasoning" | "rule_based_fallback"


_ACTION_ENUM = ["retry_nudge", "loyalty_offer", "upsell_campaign", "price_alert"]

_SYSTEM_PROMPT = (
    "You are a revenue-growth strategist for an e-commerce merchant. Given which "
    "customer/order segments currently have activity, the merchant's real product "
    "catalog (JSON: id, name, price, category), and its checkout policy, recommend "
    "concrete marketing actions.\n"
    "- Only ever target a segment name that appears in the segment summary; never "
    "invent one, and never recommend for a segment with zero orders.\n"
    "- Ground every recommendation in the actual catalog/policy given — name real "
    "products, categories, or prices in your reasoning where relevant, not generic "
    "advice.\n"
    "- suggested_discount_pct must be between 0 and 30, or null for actions that "
    "don't involve a discount (e.g. price_alert).\n"
    "- confidence (0-1) reflects how strongly the data supports the action.\n"
    "- Omit a segment you have no confident recommendation for rather than forcing one."
)


def _build_schema(segment_names: list[str], max_discount_pct: float = 30.0) -> dict:
    """target_segment is enum-constrained to segments that actually have orders this run —
    the model is structurally unable to target an empty or nonexistent segment.
    suggested_discount_pct is capped at the merchant's policy.max_discount_pct (at most 50%)."""
    ceiling = min(max(0.0, float(max_discount_pct)), 50.0)
    return {
        "type": "object",
        "properties": {
            "recommendations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": _ACTION_ENUM},
                        "target_segment": {"type": "string", "enum": segment_names},
                        "reasoning": {"type": "string"},
                        "suggested_discount_pct": {"type": ["number", "null"], "minimum": 0, "maximum": ceiling},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                    "required": ["action", "target_segment", "reasoning", "suggested_discount_pct", "confidence"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["recommendations"],
        "additionalProperties": False,
    }


def _segment_summary(segments: dict[str, list[dict]]) -> dict:
    return {
        name: {"order_count": len(orders), "total_amount": sum(o["amount"] for o in orders)}
        for name, orders in segments.items()
        if orders
    }


def _catalog_context(catalog: list[Product]) -> list[dict]:
    return [
        {"id": str(p.id), "name": p.name, "price": float(p.price), "category": p.category}
        for p in catalog
    ]


def _policy_context(policy: Policy) -> dict:
    return {
        "max_amount": float(policy.max_amount) if policy.max_amount is not None else None,
        "allowed_categories": list(policy.allowed_categories or []),
        "per_user_limit": float(policy.per_user_limit) if policy.per_user_limit is not None else None,
        "max_discount_pct": float(getattr(policy, "max_discount_pct", 30.0)),
    }


def _user_content(merchant_name: str, segment_summary: dict, catalog_context: list[dict], policy_context: dict) -> str:
    return (
        f"Merchant: {merchant_name}\n\n"
        f"Segments:\n{json.dumps(segment_summary)}\n\n"
        f"Catalog:\n{json.dumps(catalog_context)}\n\n"
        f"Policy:\n{json.dumps(policy_context)}"
    )


async def _call_anthropic(user_content: str, segment_names: list[str], max_discount_pct: float, api_key: str) -> dict:
    if not api_key:
        raise GrowthAgentUnavailable("ANTHROPIC_API_KEY is not set; growth-agent reasoning is unavailable.")

    client = anthropic.AsyncAnthropic(api_key=api_key)
    response = await client.messages.create(
        model=ANTHROPIC_MODEL_ID,
        max_tokens=4096,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
        output_config={
            "format": {"type": "json_schema", "schema": _build_schema(segment_names, max_discount_pct)},
            "effort": "low",
        },
    )

    if response.stop_reason == "max_tokens":
        raise ValueError("Growth agent response truncated.")

    text_block = next((b for b in response.content if b.type == "text"), None)
    if text_block is None:
        raise ValueError("No structured response from the model.")

    return json.loads(text_block.text)


async def _call_openai(user_content: str, segment_names: list[str], max_discount_pct: float, api_key: str) -> dict:
    if not api_key:
        raise GrowthAgentUnavailable("OPENAI_API_KEY is not set; growth-agent reasoning is unavailable.")

    client = openai.AsyncOpenAI(api_key=api_key)
    response = await client.chat.completions.create(
        model=OPENAI_MODEL_ID,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "campaign_recommendations",
                "strict": True,
                "schema": _build_schema(segment_names, max_discount_pct),
            },
        },
    )

    choice = response.choices[0]
    if choice.finish_reason == "length":
        raise ValueError("Growth agent response truncated.")

    content = choice.message.content
    if not content:
        raise ValueError("No structured response from the model.")

    return json.loads(content)


def _rule_based_fallback(segments: dict[str, list[dict]]) -> list[CampaignAction]:
    """The pre-LLM v1.3 rule map, kept verbatim as the fallback path."""
    actions: list[CampaignAction] = []
    if segments.get("failed_payment_recent"):
        actions.append(
            CampaignAction(
                action="retry_nudge",
                target_segment="failed_payment_recent",
                reasoning="Rule-based fallback: recent failed payments get a retry nudge.",
                suggested_discount_pct=None,
                confidence=1.0,
                path="rule_based_fallback",
            )
        )
    if segments.get("high_value_cart"):
        actions.append(
            CampaignAction(
                action="loyalty_offer",
                target_segment="high_value_cart",
                reasoning="Rule-based fallback: high-value carts get a loyalty offer.",
                suggested_discount_pct=None,
                confidence=1.0,
                path="rule_based_fallback",
            )
        )
    return actions


async def recommend_campaign_actions(
    segments: dict[str, list[dict]],
    merchant: Merchant,
    catalog: list[Product],
    policy: Policy,
) -> list[CampaignAction]:
    """
    Never raises — any LLM/config/parse failure falls back to the rule-based
    map rather than failing the whole campaign run (see module docstring).
    """
    present_segments = {name: orders for name, orders in segments.items() if orders}
    if not present_segments:
        return []

    settings = get_settings()
    segment_names = list(present_segments.keys())
    max_discount_pct = float(getattr(policy, "max_discount_pct", 30.0))
    user_content = _user_content(
        merchant.name, _segment_summary(present_segments), _catalog_context(catalog), _policy_context(policy)
    )

    try:
        if settings.model_provider == "anthropic":
            parsed = await _call_anthropic(user_content, segment_names, max_discount_pct, settings.anthropic_api_key)
        elif settings.model_provider == "openai":
            parsed = await _call_openai(user_content, segment_names, max_discount_pct, settings.openai_api_key)
        else:
            raise GrowthAgentUnavailable(
                f"model_provider={settings.model_provider!r} has no growth-agent implementation yet."
            )

        actions = []
        for item in parsed["recommendations"]:
            # Defense-in-depth: clamp discount to policy ceiling
            if item.get("suggested_discount_pct") is not None:
                item["suggested_discount_pct"] = min(float(item["suggested_discount_pct"]), max_discount_pct)
            actions.append(CampaignAction(**item, path="llm_reasoning"))
        return actions
    except Exception as e:
        logger.warning("Growth agent LLM call failed (%s) — falling back to rule-based recommendations.", e)
        return _rule_based_fallback(present_segments)
