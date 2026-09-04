"""
Agent discovery manifest — GET /.well-known/agent-manifest.json.

Public, unauthenticated, and registered directly on the app (see app/main.py:
no api_v1_prefix) — an external AI agent needs to fetch this *before* it has
an API key, to learn the auth/idempotency contract it must follow. Loosely
UCP/AP2-style: a flat, self-describing JSON document a tool-calling LLM can
parse and act on directly, rather than a hand-maintained subset of the
OpenAPI spec (which stays the source of truth for full schema detail — see
/docs).
"""
from fastapi import APIRouter

from app.config.settings import get_settings

router = APIRouter(tags=["discovery"])

settings = get_settings()


@router.get("/.well-known/agent-manifest.json")
async def agent_manifest() -> dict:
    prefix = settings.api_v1_prefix
    return {
        "version": "1.0",
        "name": settings.app_name,
        "description": (
            "Agentic backend that makes a Razorpay merchant AI-sellable (test-mode): an "
            "agent-readable product catalog and a policy-gated checkout endpoint."
        ),
        "endpoints": {
            "catalog": {
                "path": f"{prefix}/agent/catalog",
                "method": "GET",
                "description": "Flat, agent-readable product catalog for one merchant.",
                "query_params": {
                    "merchant_id": {
                        "type": "string",
                        "format": "uuid",
                        "required": True,
                        "description": "The merchant to list products for.",
                    },
                    "category": {
                        "type": "string",
                        "required": False,
                        "description": "Filter to products in this category.",
                    },
                    "max_price": {
                        "type": "number",
                        "required": False,
                        "description": "Filter to products priced at or below this amount.",
                    },
                },
            },
            "checkout": {
                "path": f"{prefix}/agent/checkout",
                "method": "POST",
                "description": (
                    "Policy-gated checkout: validates the cart against the live catalog, "
                    "evaluates it against the merchant's policy, and creates a Razorpay "
                    "test-mode order."
                ),
                "body": {
                    "schema_ref": "CheckoutRequest",
                    "fields": {
                        "merchant_id": {"type": "string", "format": "uuid", "required": True},
                        "cart_items": {
                            "type": "array",
                            "required": True,
                            "items": {
                                "product_id": {"type": "string", "format": "uuid", "required": True},
                                "quantity": {"type": "integer", "required": True},
                            },
                        },
                        "customer_context": {
                            "type": "object",
                            "required": False,
                            "description": (
                                "Optional. A customer_id field enables per-user policy limits."
                            ),
                        },
                    },
                },
            },
            "chat_checkout": {
                "path": f"{prefix}/agent/chat-checkout",
                "method": "POST",
                "description": (
                    "Conversational checkout: interprets a free-text shopper message "
                    "against the merchant's live catalog with an LLM, then runs the "
                    "resulting cart through the same policy-gated checkout as "
                    f"POST {prefix}/agent/checkout. Returns matched=false with a "
                    "human-readable explanation (HTTP 200) instead of an error when "
                    "the message can't be confidently mapped to a real product."
                ),
                "body": {
                    "schema_ref": "ChatCheckoutRequest",
                    "fields": {
                        "message": {
                            "type": "string",
                            "required": True,
                            "description": "The shopper's free-text request, e.g. '2x face wash under 400'.",
                        },
                        "merchant_id": {"type": "string", "format": "uuid", "required": True},
                        "customer_context": {
                            "type": "object",
                            "required": False,
                            "description": (
                                "Optional. A customer_id field enables per-user policy limits."
                            ),
                        },
                    },
                },
                "response": {
                    "schema_ref": "ChatCheckoutResponse",
                    "fields": {
                        "interpretation": {
                            "type": "string",
                            "description": "One-line human-readable explanation of how the message was interpreted (or why it wasn't).",
                        },
                        "matched": {
                            "type": "boolean",
                            "description": "False when no confident in-catalog match was found; checkoutResult is null in that case.",
                        },
                        "checkout_result": {
                            "type": "object",
                            "nullable": True,
                            "description": "Same shape as CheckoutResponse from POST /agent/checkout, present only when matched=true.",
                        },
                    },
                },
                "idempotency_note": (
                    "Idempotency-Key is optional here (unlike POST /agent/checkout): a "
                    "chat message has no natural place to carry that header, so one is "
                    "generated per call when omitted. Retrying the same message without "
                    "an explicit key is therefore NOT idempotent — pass your own key for "
                    "replay-safety."
                ),
            },
        },
        "auth": {
            "type": "api_key",
            "header": "X-Agent-Api-Key",
            "required_on": [
                f"GET {prefix}/agent/catalog",
                f"POST {prefix}/agent/checkout",
                f"POST {prefix}/agent/chat-checkout",
            ],
            "how_to_obtain": (
                f"Returned once, in the response of POST {prefix}/merchant/onboarding/keys, "
                "at merchant onboarding time. It cannot be retrieved again afterwards — "
                "store it securely. A request with a missing or invalid key gets a 401."
            ),
        },
        "idempotency": {
            "header": "Idempotency-Key",
            "required_on": [f"POST {prefix}/agent/checkout"],
            "optional_on": [f"POST {prefix}/agent/chat-checkout"],
            "description": (
                "A caller-generated unique string per checkout attempt, unique per merchant. "
                "Retrying the same logical checkout with the same key and the same cart "
                "returns the original order instead of creating a duplicate order or "
                "double-charging. A missing or empty header gets a 400 on the endpoints "
                "where it's required; reusing a key with a different cart gets a 409. On "
                "chat-checkout it's optional — see that endpoint's idempotency_note for "
                "why, and what omitting it means for retries."
            ),
        },
        "docs": "/docs",
    }
