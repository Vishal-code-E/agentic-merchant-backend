"""
Thin wrapper around Razorpay's Orders/Payments APIs (test mode only for v1).

No graph node should call the Razorpay SDK directly — always go through
this service so retries, idempotency, and error mapping stay centralized.

The `razorpay` SDK is synchronous, so every call is wrapped in
asyncio.to_thread() to avoid blocking the event loop.
"""
import asyncio
from typing import Any

import razorpay
from razorpay.errors import SignatureVerificationError


class RazorpayClient:
    def __init__(self, key_id: str, key_secret: str):
        self.key_id = key_id
        self.key_secret = key_secret
        self.client = razorpay.Client(auth=(key_id, key_secret))

    async def validate_keys(self) -> bool:
        """Probe the credentials by listing orders; returns False on any auth failure."""
        try:
            await asyncio.to_thread(self.client.order.all, {"count": 1})
            return True
        except Exception:
            return False

    async def create_order(
        self,
        amount_paise: int,
        currency: str,
        receipt: str,
        notes: dict | None = None,
    ) -> dict[str, Any]:
        """Create a test-mode Razorpay Order. amount_paise is the amount in the smallest currency unit."""
        payload = {
            "amount": amount_paise,
            "currency": currency,
            "receipt": receipt,
            "notes": notes or {},
        }
        return await asyncio.to_thread(self.client.order.create, payload)

    async def fetch_order(self, razorpay_order_id: str) -> dict[str, Any]:
        return await asyncio.to_thread(self.client.order.fetch, razorpay_order_id)

    async def verify_webhook_signature(self, body: bytes, signature: str, secret: str) -> bool:
        try:
            await asyncio.to_thread(
                self.client.utility.verify_webhook_signature,
                body.decode("utf-8"),
                signature,
                secret,
            )
            return True
        except SignatureVerificationError:
            return False
