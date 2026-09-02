"""
Thin wrapper around Razorpay's Orders/Payments APIs (test mode only for v1).

This is a stub: method signatures and docstrings are defined per the LLD,
implementations are intentionally left as TODOs for the v1.0 build day.
No graph node should call the Razorpay SDK directly — always go through
this service so retries, idempotency, and error mapping stay centralized.
"""
from typing import Any


class RazorpayClient:
    def __init__(self, key_id: str, key_secret: str):
        self.key_id = key_id
        self.key_secret = key_secret
        # TODO(v1.0): instantiate razorpay.Client(auth=(key_id, key_secret))

    async def create_order(
        self,
        amount: float,
        currency: str,
        receipt: str,
        notes: dict | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        """
        Create a test-mode Razorpay Order.
        TODO(v1.0): call self.client.order.create(...) with idempotency handling.
        """
        raise NotImplementedError

    async def fetch_order(self, razorpay_order_id: str) -> dict[str, Any]:
        """TODO(v1.0): call self.client.order.fetch(razorpay_order_id)."""
        raise NotImplementedError

    async def verify_webhook_signature(self, body: bytes, signature: str, secret: str) -> bool:
        """TODO(v1.3): verify Razorpay webhook signature for payment status updates."""
        raise NotImplementedError
