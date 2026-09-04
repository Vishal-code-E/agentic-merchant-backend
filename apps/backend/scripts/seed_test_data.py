#!/usr/bin/env python3
"""
Seeds one merchant with a 4-product catalog for manual testing — a
compliant-cart product, a policy-denial product pairing, an upsell
candidate, and a deliberately out-of-stock product, all in one place.

Prints narration to stderr and ONLY `export VAR=value` lines to stdout, so
it can be captured directly:

    eval "$(python scripts/seed_test_data.py)"

Requires RAZORPAY_TEST_KEY_ID / RAZORPAY_TEST_KEY_SECRET (test-mode) via
env — no hardcoded fallback, fails clearly if unset.

Reuses setup_demo_merchant.py's onboard_merchant()/seed_products() rather
than duplicating the onboarding/catalog HTTP calls; only the policy,
product list, and env var names differ here.
"""
from __future__ import annotations

import os
import sys

import httpx
from setup_demo_merchant import onboard_merchant, seed_products

MERCHANT_NAME = "Seed Test Co"
MAX_AMOUNT = 1200.0
ALLOWED_CATEGORIES = ["electronics", "accessories"]
PER_USER_LIMIT = 500.0

# 2x Earbuds (998) stays under max_amount; 3x Earbuds (1497) exceeds it —
# use those two carts for compliant vs. policy-denial manual tests. Speaker
# is a same-category upsell candidate alongside Earbuds. Screen Protector
# is deliberately zero-stock, for the out-of-stock rejection path.
PRODUCTS = [
    {"name": "Wireless Earbuds", "price": 499.00, "category": "electronics", "stock": 15},
    {"name": "Phone Case", "price": 199.00, "category": "accessories", "stock": 20},
    {"name": "Bluetooth Speaker", "price": 899.00, "category": "electronics", "stock": 5},
    {"name": "Screen Protector", "price": 99.00, "category": "accessories", "stock": 0},
]


def main() -> int:
    razorpay_key_id = os.environ.get("RAZORPAY_TEST_KEY_ID")
    razorpay_key_secret = os.environ.get("RAZORPAY_TEST_KEY_SECRET")
    base_url = os.environ.get("BASE_URL", "http://localhost:8000")

    if not razorpay_key_id or not razorpay_key_secret:
        print(
            "RAZORPAY_TEST_KEY_ID / RAZORPAY_TEST_KEY_SECRET must be set to your Razorpay "
            "TEST-mode key id/secret — not hardcoded, and not read from RAZORPAY_KEY_ID/SECRET.",
            file=sys.stderr,
        )
        return 1

    api = f"{base_url.rstrip('/')}/api/v1"
    client = httpx.Client(timeout=30.0)

    def narrate(msg: str) -> None:
        print(msg, file=sys.stderr)

    merchant_id, api_key = onboard_merchant(
        client, api, MERCHANT_NAME, razorpay_key_id, razorpay_key_secret,
        MAX_AMOUNT, ALLOWED_CATEGORIES, PER_USER_LIMIT, narrate,
    )
    created = seed_products(client, api, merchant_id, PRODUCTS, narrate)

    narrate("✅ Seed data ready.\n")
    narrate("Product ids:")
    name_width = max(len(p["name"]) for p in created)
    for p in created:
        narrate(f"  {p['name']:<{name_width}}  {p['id']}")
    narrate("")

    print(f"export MERCHANT_ID={merchant_id}")
    print(f"export AGENT_API_KEY={api_key}")
    print(f"export BASE_URL={base_url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
