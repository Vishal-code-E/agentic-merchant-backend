"""Typed state objects for LangGraph graphs — explicit, not implicit (see Graph Engineering doc §2.4)."""
from typing import Any, TypedDict


class CheckoutState(TypedDict, total=False):
    merchant_id: str
    customer_context: dict[str, Any] | None
    cart_items: list[dict[str, Any]]
    constraints: dict[str, Any]
    upsell_suggestions: list[dict[str, Any]] | None
    policy_result: dict[str, Any] | None
    order_id: str | None
    razorpay_order_id: str | None
    amount: float | None
    currency: str | None
    status: str  # pending | success | failed
    #: Which node set status="failed". The router maps this to an HTTP status,
    #: since a policy denial and a bad cart are both status="failed" but are
    #: 403 and 400 respectively.
    #: validate_cart | policy | policy_missing | create_order
    failure_stage: str | None
    explanation: str | None


class CampaignState(TypedDict, total=False):
    merchant_id: str
    time_window: dict[str, Any]
    orders: list[dict[str, Any]]
    segments: dict[str, list[str]]
    actions: list[dict[str, Any]]
    status: str
