#!/usr/bin/env python3
"""
One-shot demo setup: onboards a merchant and seeds a small catalog, entirely
over HTTP (same contract any external caller would use).

Prints narration to stderr and ONLY `export VAR=value` lines to stdout, so it
can be captured directly:

    eval "$(python scripts/setup_demo_merchant.py)"

Requires RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET (test-mode) via env or flags —
see docs/DEMO.md.

Catalog/policy numbers are chosen deliberately, not arbitrary: max_amount=700
with Face Wash at 380 means the demo purchase alone clears campaign_graph's
high-value threshold (0.5 * max_amount), so `POST /internal/campaigns/run`
has something real to recommend later in the demo.
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Callable

import httpx

DEMO_MAX_AMOUNT = 700.0
DEMO_PRODUCTS = [
    {"name": "Face Wash", "price": 380, "category": "skincare", "stock": 50},
    {"name": "Moisturizer", "price": 420, "category": "skincare", "stock": 50},
]


def onboard_merchant(
    client: httpx.Client,
    api: str,
    name: str,
    razorpay_key_id: str,
    razorpay_key_secret: str,
    max_amount: float,
    allowed_categories: list[str],
    per_user_limit: float | None,
    narrate: Callable[[str], None],
) -> tuple[str, str]:
    """POST /merchant/onboarding/keys; returns (merchant_id, api_key). Shared with seed_test_data.py."""
    narrate(f"🏗️  Onboarding {name!r}...")
    payload = {
        "name": name,
        "razorpay_key_id": razorpay_key_id,
        "razorpay_key_secret": razorpay_key_secret,
        "max_amount": max_amount,
        "allowed_categories": allowed_categories,
        "per_user_limit": per_user_limit,
    }
    resp = client.post(f"{api}/merchant/onboarding/keys", json=payload)
    resp.raise_for_status()
    onboarded = resp.json()

    if not onboarded["keys_valid"]:
        narrate("⚠️  Razorpay key validation failed — checkout calls later will error. Check your test keys.")
    merchant_id = onboarded["merchant"]["id"]
    narrate(f"   merchant_id={merchant_id}")

    return merchant_id, onboarded["api_key"]


def seed_products(
    client: httpx.Client,
    api: str,
    merchant_id: str,
    products: list[dict],
    narrate: Callable[[str], None],
) -> list[dict]:
    """POST /merchant/products for each entry; returns the created ProductResponse bodies (real ids)."""
    narrate("🛍️  Seeding catalog...")
    created = []
    for product in products:
        payload = {"merchant_id": merchant_id, "currency": "INR", "tags": [], **product}
        resp = client.post(f"{api}/merchant/products", json=payload)
        resp.raise_for_status()
        created.append(resp.json())
        narrate(f"   + {product['name']} — {product['price']} INR ({product['category']})")
    return created


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Onboard a demo merchant + catalog for docs/DEMO.md.")
    parser.add_argument("--name", default="Demo Skincare Co")
    parser.add_argument("--razorpay-key-id", default=os.environ.get("RAZORPAY_KEY_ID"))
    parser.add_argument("--razorpay-key-secret", default=os.environ.get("RAZORPAY_KEY_SECRET"))
    parser.add_argument("--base-url", default=os.environ.get("BASE_URL", "http://localhost:8000"))
    args = parser.parse_args()
    if not args.razorpay_key_id or not args.razorpay_key_secret:
        parser.error(
            "--razorpay-key-id/--razorpay-key-secret are required (or set RAZORPAY_KEY_ID / "
            "RAZORPAY_KEY_SECRET) — use your Razorpay TEST-mode keys."
        )
    return args


def main() -> int:
    args = parse_args()
    api = f"{args.base_url.rstrip('/')}/api/v1"
    client = httpx.Client(timeout=30.0)

    def narrate(msg: str) -> None:
        print(msg, file=sys.stderr)

    merchant_id, api_key = onboard_merchant(
        client, api, args.name, args.razorpay_key_id, args.razorpay_key_secret,
        DEMO_MAX_AMOUNT, [], None, narrate,
    )
    seed_products(client, api, merchant_id, DEMO_PRODUCTS, narrate)

    narrate("✅ Demo merchant ready.\n")

    print(f"export MERCHANT_ID={merchant_id}")
    print(f"export AGENT_API_KEY={api_key}")
    print(f"export BASE_URL={args.base_url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
