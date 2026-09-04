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

import httpx

DEMO_MAX_AMOUNT = 700.0
DEMO_PRODUCTS = [
    {"name": "Face Wash", "price": 380, "category": "skincare", "stock": 50},
    {"name": "Moisturizer", "price": 420, "category": "skincare", "stock": 50},
]


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

    narrate(f"🏗️  Onboarding {args.name!r} against {args.base_url}...")
    onboard_payload = {
        "name": args.name,
        "razorpay_key_id": args.razorpay_key_id,
        "razorpay_key_secret": args.razorpay_key_secret,
        "max_amount": DEMO_MAX_AMOUNT,
        "allowed_categories": [],
        "per_user_limit": None,
    }
    resp = client.post(f"{api}/merchant/onboarding/keys", json=onboard_payload)
    resp.raise_for_status()
    onboarded = resp.json()
    merchant_id = onboarded["merchant"]["id"]
    api_key = onboarded["api_key"]

    if not onboarded["keys_valid"]:
        narrate("⚠️  Razorpay key validation failed — checkout calls later will error. Check your test keys.")
    narrate(f"   merchant_id={merchant_id}")

    narrate("🛍️  Seeding catalog...")
    for product in DEMO_PRODUCTS:
        payload = {"merchant_id": merchant_id, "currency": "INR", "tags": [], **product}
        resp = client.post(f"{api}/merchant/products", json=payload)
        resp.raise_for_status()
        narrate(f"   + {product['name']} — {product['price']} INR ({product['category']})")

    narrate("✅ Demo merchant ready.\n")

    print(f"export MERCHANT_ID={merchant_id}")
    print(f"export AGENT_API_KEY={api_key}")
    print(f"export BASE_URL={args.base_url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
