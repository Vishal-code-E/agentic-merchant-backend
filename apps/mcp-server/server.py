"""
Razorpay Agentic Merchant MCP Server.

Exposes agentic e-commerce capabilities as first-class MCP tools:
1. catalog_tool: Search and browse agent-readable product catalogs with category/price filters.
2. checkout_tool: Execute policy-gated checkouts against Razorpay test-mode orders.
3. chat_checkout_tool: Conversational checkout translating free-text buyer intent into structured carts and orders.

Authentication Model:
- Hybrid Architecture:
  - Single-Tenant Default: Reads DEFAULT_MERCHANT_ID and DEFAULT_AGENT_API_KEY from environment.
    Allows Claude Desktop or local agents to call tools without specifying merchant credentials.
  - Multi-Tenant Pass-Through: Each tool accepts optional `merchant_id` and `agent_api_key` arguments.
    If provided, they override the environment defaults on a per-call basis.
"""
import argparse
import uuid
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from settings import get_mcp_settings

# Initialize FastMCP application
mcp = FastMCP(
    "Razorpay Agentic Merchant",
    dependencies=["httpx", "pydantic", "pydantic-settings"],
)


class CartItemInput(BaseModel):
    product_id: str = Field(description="UUID of the product to purchase")
    quantity: int = Field(default=1, gt=0, description="Quantity to purchase (must be > 0)")


def _resolve_auth(
    merchant_id: str | None = None,
    agent_api_key: str | None = None,
) -> tuple[str, str]:
    """Resolve effective merchant_id and agent_api_key from args or environment."""
    settings = get_mcp_settings()
    effective_merchant_id = merchant_id or settings.default_merchant_id
    effective_api_key = agent_api_key or settings.default_agent_api_key

    if not effective_merchant_id:
        raise ValueError(
            "No merchant_id provided and DEFAULT_MERCHANT_ID is not set in MCP server config. "
            "Pass merchant_id in tool arguments or configure DEFAULT_MERCHANT_ID."
        )
    if not effective_api_key:
        raise ValueError(
            "No agent_api_key provided and DEFAULT_AGENT_API_KEY is not set in MCP server config. "
            "Pass agent_api_key in tool arguments or configure DEFAULT_AGENT_API_KEY."
        )

    return effective_merchant_id, effective_api_key


def _handle_http_error(err: httpx.HTTPStatusError) -> dict[str, Any]:
    """Map HTTP status codes into structured, explainable tool outputs."""
    status_code = err.response.status_code
    try:
        data = err.response.json()
        detail = data.get("detail", str(data))
    except Exception:
        detail = err.response.text or str(err)

    remedy_map = {
        400: "Check cart format, message length (max 500 chars), or required parameters.",
        401: "Invalid or missing X-Agent-Api-Key. Verify agent_api_key matches the onboarded merchant key.",
        403: "Policy denial: Cart total exceeds merchant's max_amount or includes prohibited categories.",
        404: "Merchant or product not found.",
        409: "Policy missing (merchant predates guardrails) or idempotency conflict with mismatched cart.",
        422: "Validation error: Check parameter types, limits, or UUID formatting.",
        429: "Rate limit reached. Please wait before retrying.",
        502: "Razorpay test-mode API failure or upstream network error.",
        503: "Conversational intent parser service is temporarily unavailable.",
    }

    remedy = remedy_map.get(status_code, "Check backend logs or verify network connectivity.")

    return {
        "error": True,
        "status_code": status_code,
        "detail": detail,
        "remedy": remedy,
    }


@mcp.tool(
    name="catalog_tool",
    description=(
        "Fetch the merchant's live, agent-readable product catalog. Supports filtering "
        "by product category and maximum price. Returns product names, prices, stock, "
        "and descriptions."
    ),
)
async def catalog_tool(
    category: str | None = None,
    max_price: float | None = None,
    merchant_id: str | None = None,
    agent_api_key: str | None = None,
) -> dict[str, Any]:
    """
    Args:
        category: Optional product category filter (e.g. 'skincare', 'electronics').
        max_price: Optional maximum price ceiling.
        merchant_id: Merchant UUID (defaults to DEFAULT_MERCHANT_ID if configured).
        agent_api_key: Merchant agent API key (defaults to DEFAULT_AGENT_API_KEY if configured).
    """
    settings = get_mcp_settings()
    try:
        eff_merchant_id, eff_api_key = _resolve_auth(merchant_id, agent_api_key)
    except ValueError as e:
        return {"error": True, "detail": str(e)}

    params: dict[str, Any] = {"merchant_id": eff_merchant_id}
    if category:
        params["category"] = category
    if max_price is not None:
        params["max_price"] = max_price

    headers = {
        "X-Agent-Api-Key": eff_api_key,
        "X-Agent-Name": "mcp-server",
        "X-Agent-Version": "0.1.0",
    }

    url = f"{settings.api_url}/agent/catalog"
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            items = resp.json()
            return {
                "success": True,
                "merchant_id": eff_merchant_id,
                "product_count": len(items),
                "products": items,
            }
    except httpx.HTTPStatusError as e:
        return _handle_http_error(e)
    except httpx.TimeoutException:
        return {"error": True, "detail": f"Request to backend timed out after {settings.request_timeout_seconds}s."}
    except httpx.ConnectError:
        return {"error": True, "detail": f"Could not connect to backend server at {settings.backend_base_url}."}
    except Exception as e:
        return {"error": True, "detail": f"Unexpected error during catalog fetch: {str(e)}"}


@mcp.tool(
    name="checkout_tool",
    description=(
        "Execute a policy-gated structured checkout for products in the merchant's catalog. "
        "Verifies stock, checks policy ceilings and category rules, offers intelligent "
        "upsell suggestions, and creates a Razorpay test-mode Order if authorised."
    ),
)
async def checkout_tool(
    cart_items: list[dict[str, Any]],
    customer_id: str | None = None,
    idempotency_key: str | None = None,
    merchant_id: str | None = None,
    agent_api_key: str | None = None,
) -> dict[str, Any]:
    """
    Args:
        cart_items: List of cart items, each with 'product_id' (UUID) and 'quantity' (int >= 1).
                    Example: [{'product_id': '45f3c...', 'quantity': 2}]
        customer_id: Optional unique customer identifier for per-user policy limit checks.
        idempotency_key: Unique idempotency key (auto-generated UUID if omitted).
        merchant_id: Merchant UUID (defaults to DEFAULT_MERCHANT_ID if configured).
        agent_api_key: Merchant agent API key (defaults to DEFAULT_AGENT_API_KEY if configured).
    """
    settings = get_mcp_settings()
    try:
        eff_merchant_id, eff_api_key = _resolve_auth(merchant_id, agent_api_key)
    except ValueError as e:
        return {"error": True, "detail": str(e)}

    # Validate cart items
    if not cart_items:
        return {"error": True, "detail": "cart_items list cannot be empty."}

    normalized_cart = []
    for item in cart_items:
        p_id = item.get("product_id") or item.get("productId")
        qty = item.get("quantity", 1)
        if not p_id:
            return {"error": True, "detail": "Each item in cart_items must have a product_id."}
        normalized_cart.append({"productId": str(p_id), "quantity": int(qty)})

    eff_idempotency_key = idempotency_key or str(uuid.uuid4())
    payload: dict[str, Any] = {
        "merchantId": eff_merchant_id,
        "cartItems": normalized_cart,
    }
    if customer_id:
        payload["customerContext"] = {"customer_id": customer_id}

    headers = {
        "X-Agent-Api-Key": eff_api_key,
        "Idempotency-Key": eff_idempotency_key,
        "X-Agent-Name": "mcp-server",
        "X-Agent-Version": "0.1.0",
    }

    url = f"{settings.api_url}/agent/checkout"
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return {
                "success": True,
                "status": data.get("status"),
                "razorpay_order_id": data.get("razorpayOrderId"),
                "amount": data.get("amount"),
                "currency": data.get("currency"),
                "explanation": data.get("explanation"),
                "upsell_suggestions": data.get("upsellSuggestions", []),
                "idempotency_key": eff_idempotency_key,
            }
    except httpx.HTTPStatusError as e:
        return _handle_http_error(e)
    except httpx.TimeoutException:
        return {"error": True, "detail": f"Request to backend timed out after {settings.request_timeout_seconds}s."}
    except httpx.ConnectError:
        return {"error": True, "detail": f"Could not connect to backend server at {settings.backend_base_url}."}
    except Exception as e:
        return {"error": True, "detail": f"Unexpected error during checkout: {str(e)}"}


@mcp.tool(
    name="chat_checkout_tool",
    description=(
        "Execute a conversational checkout directly from a customer's free-text request "
        "(e.g., 'buy 2 face wash under 400'). Uses an LLM constrained strictly to the "
        "merchant's live catalog to parse intent, then executes the full policy-gated "
        "checkout flow. Returns matched=false when the request cannot be satisfied."
    ),
)
async def chat_checkout_tool(
    message: str,
    customer_id: str | None = None,
    idempotency_key: str | None = None,
    merchant_id: str | None = None,
    agent_api_key: str | None = None,
) -> dict[str, Any]:
    """
    Args:
        message: Shopper's natural language request (max 500 characters).
        customer_id: Optional unique customer identifier for per-user policy limit checks.
        idempotency_key: Optional idempotency key for replay-safety.
        merchant_id: Merchant UUID (defaults to DEFAULT_MERCHANT_ID if configured).
        agent_api_key: Merchant agent API key (defaults to DEFAULT_AGENT_API_KEY if configured).
    """
    settings = get_mcp_settings()
    try:
        eff_merchant_id, eff_api_key = _resolve_auth(merchant_id, agent_api_key)
    except ValueError as e:
        return {"error": True, "detail": str(e)}

    if not message or not message.strip():
        return {"error": True, "detail": "message cannot be empty."}

    if len(message) > 500:
        return {"error": True, "detail": f"message exceeds 500 character limit ({len(message)} chars)."}

    payload: dict[str, Any] = {
        "merchantId": eff_merchant_id,
        "message": message.strip(),
    }
    if customer_id:
        payload["customerContext"] = {"customer_id": customer_id}

    headers = {
        "X-Agent-Api-Key": eff_api_key,
        "X-Agent-Name": "mcp-server",
        "X-Agent-Version": "0.1.0",
    }
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key

    url = f"{settings.api_url}/agent/chat-checkout"
    try:
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            return {
                "success": True,
                "matched": data.get("matched", False),
                "interpretation": data.get("interpretation", ""),
                "checkout_result": data.get("checkoutResult"),
            }
    except httpx.HTTPStatusError as e:
        return _handle_http_error(e)
    except httpx.TimeoutException:
        return {"error": True, "detail": f"Request to backend timed out after {settings.request_timeout_seconds}s."}
    except httpx.ConnectError:
        return {"error": True, "detail": f"Could not connect to backend server at {settings.backend_base_url}."}
    except Exception as e:
        return {"error": True, "detail": f"Unexpected error during conversational checkout: {str(e)}"}


def main():
    parser = argparse.ArgumentParser(description="Razorpay Agentic Merchant MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport protocol: 'stdio' for Claude Desktop / CLI, 'sse' for HTTP streaming (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="Port for SSE transport (default: 8001)",
    )
    args = parser.parse_args()

    if args.transport == "sse":
        print(f"Starting Razorpay Agentic Merchant MCP Server with SSE transport on port {args.port}...")
        mcp.settings.port = args.port
        mcp.run(transport="sse")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
