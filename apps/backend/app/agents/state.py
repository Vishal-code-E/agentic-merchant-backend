"""Typed state objects for LangGraph graphs — explicit, not implicit (see Graph Engineering doc §2.4)."""
from typing import Any, TypedDict


class CheckoutState(TypedDict, total=False):
    merchant_id: str
    customer_context: dict[str, Any] | None
    cart_items: list[dict[str, Any]]
    constraints: dict[str, Any]
    #: Set by router_checkout before invoking the graph; nodes use it to tag
    #: audit_logs rows against the right AgentRun.
    agent_run_id: str | None
    #: Caller's Idempotency-Key header (router_checkout 400s before invoking
    #: the graph if it's missing, so by the time a node sees this it's always
    #: set). create_order_node checks it against Order.idempotency_key before
    #: calling Razorpay.
    idempotency_key: str
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
    #: Set by router_campaigns before invoking the graph; used to tag
    #: audit_logs rows against the right AgentRun.
    agent_run_id: str | None
    window_hours: int
    #: Raw orders loaded by LoadOrders (id, status, amount, currency, cart_snapshot).
    orders: list[dict[str, Any]]
    #: SegmentCustomers output — "failed_payment_recent" | "high_value_cart" -> orders.
    #: Order has no customer_id column, so these are order-level, not
    #: customer-level, segments (see campaign_graph.py's module docstring).
    segments: dict[str, list[dict[str, Any]]]
    #: RecommendActions output, before the ApplyPolicy filter — one dict per
    #: order, each carrying reasoning/confidence/suggested_discount_pct/path
    #: from growth_agent.recommend_campaign_actions (see campaign_graph.py).
    recommended_actions: list[dict[str, Any]]
    #: ApplyPolicy output — recommended_actions that survived PolicyEngine.evaluate().
    #: This is what EmitAudit logs and the endpoint returns.
    actions: list[dict[str, Any]]
    status: str
