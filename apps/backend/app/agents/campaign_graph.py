"""
campaign_graph: LoadOrders -> SegmentCustomers -> RecommendActions -> ApplyPolicy -> EmitAudit

Background revenue workflow, triggered manually for now via
POST /internal/campaigns/run (see app/api/router_campaigns.py). v1.3 scope is
rule-based only — no LLM call anywhere in this graph.

KNOWN GAP: Order has no customer_id column (see policy_engine.py's own note on
per_user_limit), so segmentation and recommendations operate on orders, not
identified customers — there is no way to actually address "the customer of
this order" yet. Closing this needs a customer_id column on Order.
"""
import uuid
from datetime import datetime, timedelta, timezone

from langgraph.graph import END, StateGraph
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.state import CampaignState
from app.models.order import Order
from app.models.policy import Policy
from app.services.audit_service import AuditService
from app.services.policy_engine import PolicyEngine

DEFAULT_WINDOW_HOURS = 24
#: high_value_cart threshold, as a fraction of the merchant's policy max_amount.
HIGH_VALUE_FRACTION = 0.5


async def _load_policy(db: AsyncSession, merchant_id: str) -> Policy | None:
    result = await db.execute(
        select(Policy).where(Policy.merchant_id == uuid.UUID(merchant_id)).limit(1)
    )
    return result.scalars().first()


async def load_orders_node(state: CampaignState, db: AsyncSession) -> CampaignState:
    """Query Postgres (not Razorpay) for the merchant's orders in the last window_hours."""
    merchant_id = state["merchant_id"]
    window_hours = state.get("window_hours") or DEFAULT_WINDOW_HOURS
    since = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    result = await db.execute(
        select(Order).where(
            Order.merchant_id == uuid.UUID(merchant_id),
            Order.created_at >= since,
        )
    )
    orders = result.scalars().all()

    state["orders"] = [
        {
            "id": str(order.id),
            "status": order.status,
            "amount": float(order.amount),
            "currency": order.currency,
            "cart_snapshot": order.cart_snapshot or {},
        }
        for order in orders
    ]
    return state


async def segment_customers_node(state: CampaignState, db: AsyncSession) -> CampaignState:
    """
    Two rule-based segments:
      - failed_payment_recent: status == "failed" (within the window
        load_orders_node already applied)
      - high_value_cart: amount > policy.max_amount * HIGH_VALUE_FRACTION

    high_value_cart is left empty if the merchant has no policy (or no
    max_amount) to derive a threshold from — ApplyPolicy fails closed on that
    same merchant regardless, so nothing would survive to EmitAudit anyway.
    """
    orders = state.get("orders") or []

    failed_payment_recent = [o for o in orders if o["status"] == "failed"]

    high_value_cart: list[dict] = []
    policy = await _load_policy(db, state["merchant_id"])
    if policy is not None and policy.max_amount is not None:
        threshold = float(policy.max_amount) * HIGH_VALUE_FRACTION
        high_value_cart = [o for o in orders if o["amount"] > threshold]

    state["segments"] = {
        "failed_payment_recent": failed_payment_recent,
        "high_value_cart": high_value_cart,
    }
    return state


async def recommend_actions_node(state: CampaignState) -> CampaignState:
    """
    Rule-based only, no LLM call:
      failed_payment_recent -> "retry_nudge"
      high_value_cart       -> "upsell_followup"

    An order present in both segments gets both recommendations; ApplyPolicy
    judges each independently.
    """
    segments = state.get("segments") or {}
    recommended: list[dict] = []

    for order in segments.get("failed_payment_recent", []):
        recommended.append(
            {
                "order_id": order["id"],
                "segment": "failed_payment_recent",
                "action": "retry_nudge",
                "amount": order["amount"],
                "currency": order["currency"],
            }
        )

    for order in segments.get("high_value_cart", []):
        recommended.append(
            {
                "order_id": order["id"],
                "segment": "high_value_cart",
                "action": "upsell_followup",
                "amount": order["amount"],
                "currency": order["currency"],
            }
        )

    state["recommended_actions"] = recommended
    return state


async def apply_policy_node(state: CampaignState, db: AsyncSession) -> CampaignState:
    """
    Reuses PolicyEngine.evaluate() — the same gate checkout_graph's
    check_policy_node uses — instead of a second, divergent policy check. Each
    recommended action is re-evaluated against its order's own original cart
    (from Order.cart_snapshot["items"], populated by create_order_node since
    v1.2), so a policy change since the original checkout is honoured.

    Fails closed: no policy row for the merchant means every recommended
    action is dropped.
    """
    recommended = state.get("recommended_actions") or []
    policy_row = await _load_policy(db, state["merchant_id"])

    if policy_row is None:
        state["actions"] = []
        return state

    policy = {
        "max_amount": policy_row.max_amount,
        "allowed_categories": list(policy_row.allowed_categories or []),
        "per_user_limit": policy_row.per_user_limit,
    }

    orders_by_id = {o["id"]: o for o in state.get("orders") or []}
    engine = PolicyEngine()
    kept: list[dict] = []

    for action in recommended:
        order = orders_by_id.get(action["order_id"]) or {}
        cart_items = order.get("cart_snapshot", {}).get("items", [])
        decision = engine.evaluate(cart_items, policy, customer_context=None)
        if decision.allowed:
            kept.append(action)

    state["actions"] = kept
    return state


async def emit_audit_node(state: CampaignState, db: AsyncSession) -> CampaignState:
    """audit_service.log_event(event_type="campaign_recommendation") for every
    action that survived ApplyPolicy."""
    audit_service = AuditService(db)
    agent_run_id = state.get("agent_run_id")

    for action in state.get("actions") or []:
        await audit_service.log_event(
            agent_run_id=agent_run_id,
            event_type="campaign_recommendation",
            payload=action,
        )

    state["status"] = "success"
    return state


def build_campaign_graph(db: AsyncSession):
    """
    Wire the v1.3 path:

        LoadOrders -> SegmentCustomers -> RecommendActions -> ApplyPolicy -> EmitAudit

    Linear — nothing here short-circuits a request the way checkout_graph's
    gates do; ApplyPolicy drops individual actions rather than failing the run.
    """

    async def _load_orders(state: CampaignState) -> CampaignState:
        return await load_orders_node(state, db)

    async def _segment_customers(state: CampaignState) -> CampaignState:
        return await segment_customers_node(state, db)

    async def _apply_policy(state: CampaignState) -> CampaignState:
        return await apply_policy_node(state, db)

    async def _emit_audit(state: CampaignState) -> CampaignState:
        return await emit_audit_node(state, db)

    graph = StateGraph(CampaignState)
    graph.add_node("load_orders", _load_orders)
    graph.add_node("segment_customers", _segment_customers)
    graph.add_node("recommend_actions", recommend_actions_node)
    graph.add_node("apply_policy", _apply_policy)
    graph.add_node("emit_audit", _emit_audit)

    graph.set_entry_point("load_orders")
    graph.add_edge("load_orders", "segment_customers")
    graph.add_edge("segment_customers", "recommend_actions")
    graph.add_edge("recommend_actions", "apply_policy")
    graph.add_edge("apply_policy", "emit_audit")
    graph.add_edge("emit_audit", END)

    return graph.compile()
