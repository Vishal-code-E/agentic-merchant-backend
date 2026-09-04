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
        },
        "auth": {
            "type": "api_key",
            "header": "X-Agent-Api-Key",
            "required_on": [f"GET {prefix}/agent/catalog", f"POST {prefix}/agent/checkout"],
            "how_to_obtain": (
                f"Returned once, in the response of POST {prefix}/merchant/onboarding/keys, "
                "at merchant onboarding time. It cannot be retrieved again afterwards — "
                "store it securely. A request with a missing or invalid key gets a 401."
            ),
        },
        "idempotency": {
            "header": "Idempotency-Key",
            "required_on": [f"POST {prefix}/agent/checkout"],
            "description": (
                "A caller-generated unique string per checkout attempt. Retrying the same "
                "logical checkout with the same key returns the original order instead of "
                "creating a duplicate order or double-charging. A request with a missing "
                "header gets a 400."
            ),
        },
        "docs": "/docs",
    }
