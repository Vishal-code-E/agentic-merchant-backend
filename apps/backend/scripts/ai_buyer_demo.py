#!/usr/bin/env python3
"""
Standalone demo script that plays the role of an external AI shopping agent.

It talks to the API exactly like any third-party agent integration would —
plain HTTP calls via httpx, no imports from `app` — and narrates each step so
it doubles as a live demo, not just a smoke test:

    1. Discovers the merchant's catalog (GET /agent/catalog)
    2. Checks the merchant's policy, to know what a compliant cart looks like
    3. Builds a compliant cart and checks out (POST /agent/checkout) — success case
    4. Builds a cart that deliberately exceeds max_amount and checks out again
       — failure case, prints the policy denial reason

Usage:
    python scripts/ai_buyer_demo.py --merchant-id <uuid> [--base-url http://localhost:8000]

Or via env vars:
    MERCHANT_ID=<uuid> BASE_URL=http://localhost:8000 python scripts/ai_buyer_demo.py

Get a merchant_id by onboarding one first: POST /merchant/onboarding/keys,
or the /onboarding dashboard page.
"""
from __future__ import annotations

import argparse
import math
import os
import sys

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Demo an AI shopping agent discovering a catalog and checking out.",
    )
    parser.add_argument(
        "--merchant-id",
        default=os.environ.get("MERCHANT_ID"),
        help="Merchant UUID to shop against (or set the MERCHANT_ID env var).",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("BASE_URL", "http://localhost:8000"),
        help="Backend base URL (or set the BASE_URL env var). Default: http://localhost:8000",
    )
    args = parser.parse_args()
    if not args.merchant_id:
        parser.error(
            "--merchant-id is required (or set the MERCHANT_ID env var). "
            "Get one from POST /merchant/onboarding/keys or the /onboarding dashboard page."
        )
    return args


def _error_detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        return resp.text
    detail = body.get("detail")
    return detail if isinstance(detail, str) else str(detail)


def main() -> int:
    args = parse_args()
    api = f"{args.base_url.rstrip('/')}/api/v1"
    client = httpx.Client(timeout=30.0)

    print(f"🤖 AI buyer agent starting up — merchant_id={args.merchant_id}, backend={args.base_url}\n")

    # --- Discover catalog ----------------------------------------------------
    print("🔍 Discovering catalog...")
    resp = client.get(f"{api}/agent/catalog", params={"merchant_id": args.merchant_id})
    resp.raise_for_status()
    catalog = resp.json()

    if not catalog:
        print("   No products found for this merchant. Add some via the /catalog dashboard page first.")
        return 1

    for item in catalog:
        print(
            f"   • {item['name']} — {item['price']} {item['currency']} "
            f"(category={item['category']!r}, stock={item['stock']})"
        )
    print()

    # --- Check policy, so we know how to build both a compliant and a violating cart ---
    print("📜 Checking merchant policy...")
    resp = client.get(f"{api}/merchant/{args.merchant_id}/policy")
    resp.raise_for_status()
    policy = resp.json()
    max_amount = policy.get("maxAmount")
    print(
        f"   max_amount={max_amount}, allowed_categories={policy.get('allowedCategories')}, "
        f"per_user_limit={policy.get('perUserLimit')}\n"
    )

    # --- Success case: pick the cheapest product, buy 1 ----------------------
    product = min(catalog, key=lambda p: p["price"])
    print(f"🛒 Building cart: 1x {product['name']} ({product['price']} {product['currency']})")
    print("💳 Calling checkout...")
    payload = {
        "merchant_id": args.merchant_id,
        "cart_items": [{"product_id": product["id"], "quantity": 1}],
        "customer_context": {"customer_id": "demo-buyer-agent"},
    }
    resp = client.post(f"{api}/agent/checkout", json=payload)
    if resp.status_code < 400:
        order = resp.json()
        print(f"✅ Order created: {order.get('razorpayOrderId')} — {order.get('amount')} {order.get('currency')}")
        print(f"   Explanation: {order.get('explanation')}")
        if order.get("upsellSuggestions"):
            names = ", ".join(u["name"] for u in order["upsellSuggestions"])
            print(f"   💡 Upsell suggestions offered: {names}")
    else:
        print(f"❌ Unexpected denial on what should have been a valid cart: {_error_detail(resp)}")
    print()

    # --- Failure case: deliberately exceed max_amount -------------------------
    if max_amount is None:
        print(
            "⚠️  Merchant policy has no max_amount configured — skipping the deliberate-denial demo "
            "(every checkout would 403 for a different reason: PolicyEngine fails closed on a missing max_amount)."
        )
        return 0

    price = float(product["price"])
    over_budget_qty = math.floor(float(max_amount) / price) + 1 if price > 0 else 1
    print(f"🛒 Building a cart that deliberately exceeds max_amount: {over_budget_qty}x {product['name']}")
    print("💳 Calling checkout (expecting a policy denial)...")
    bad_payload = {
        "merchant_id": args.merchant_id,
        "cart_items": [{"product_id": product["id"], "quantity": over_budget_qty}],
        "customer_context": {"customer_id": "demo-buyer-agent"},
    }
    resp = client.post(f"{api}/agent/checkout", json=bad_payload)
    if resp.status_code >= 400:
        print(f"❌ Denied ({resp.status_code}): {_error_detail(resp)}")
    else:
        print("⚠️  Expected a denial but checkout succeeded — policy may be more permissive than assumed.")
        print(f"   {resp.json()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
