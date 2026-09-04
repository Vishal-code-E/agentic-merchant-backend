"""
campaign_graph: LoadOrders -> SegmentCustomers -> RecommendActions -> ApplyPolicy -> EmitAudit

Background revenue workflow, triggered manually for now via
POST /internal/campaigns/run (see app/api/router_campaigns.py). RecommendActions
is LLM-reasoned as of this version (see app/services/growth_agent.py), with a
rule-based fallback — every other node is unchanged from the v1.3 rule-based build.

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
from app.models.merchant import Merchant
from app.models.order import Order
from app.models.policy import Policy
from app.models.product import Product
from app.services.audit_service import AuditService
from app.services.growth_agent import recommend_campaign_actions
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


async def recommend_actions_node(state: CampaignState, db: AsyncSession) -> CampaignState:
    """
    LLM-reasoned via growth_agent.recommend_campaign_actions (falls back to the
    old rule-based map internally on any failure — see that module). It reasons
    per segment, not per order; this node expands each segment-level
    recommendation into one action per order in that segment, so ApplyPolicy
    (unchanged) can still judge each against its own order's cart.

    No policy/merchant row means ApplyPolicy would drop everything anyway, so
    the LLM call is skipped rather than reasoning over a dead end.
    """
    segments = state.get("segments") or {}
    merchant_id = uuid.UUID(state["merchant_id"])

    merchant = await db.get(Merchant, merchant_id)
    policy_row = await _load_policy(db, state["merchant_id"])
    if merchant is None or policy_row is None:
        state["recommended_actions"] = []
        return state

    catalog_result = await db.execute(
        select(Product).where(Product.merchant_id == merchant_id, Product.stock > 0)
    )
    catalog = catalog_result.scalars().all()

    campaign_actions = await recommend_campaign_actions(segments, merchant, catalog, policy_row)

    recommended: list[dict] = []
    for rec in campaign_actions:
        for order in segments.get(rec.target_segment, []):
            recommended.append(
                {
                    "order_id": order["id"],
                    "segment": rec.target_segment,
                    "action": rec.action,
                    "amount": order["amount"],
                    "currency": order["currency"],
                    "reasoning": rec.reasoning,
                    "confidence": rec.confidence,
                    "suggested_discount_pct": rec.suggested_discount_pct,
                    "path": rec.path,
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

    max_discount_pct = float(getattr(policy_row, "max_discount_pct", 30.0))
    policy = {
        "max_amount": policy_row.max_amount,
        "allowed_categories": list(policy_row.allowed_categories or []),
        "per_user_limit": policy_row.per_user_limit,
        "max_discount_pct": max_discount_pct,
    }

    orders_by_id = {o["id"]: o for o in state.get("orders") or []}
    engine = PolicyEngine()
    kept: list[dict] = []

    for action in recommended:
        # Discount guardrail: discard any recommendation exceeding policy discount ceiling
        suggested_pct = action.get("suggested_discount_pct")
        if suggested_pct is not None and float(suggested_pct) > max_discount_pct:
            continue

        order = orders_by_id.get(action["order_id"]) or {}
        cart_items = order.get("cart_snapshot", {}).get("items", [])
        decision = engine.evaluate(cart_items, policy, customer_context=None)
        if decision.allowed:
            kept.append(action)

    state["actions"] = kept
    return state


async def emit_audit_node(state: CampaignState, db: AsyncSession) -> CampaignState:
    """audit_service.log_event(event_type="campaign_recommendation") for every
    action that survived ApplyPolicy — payload=action already carries reasoning/
    confidence/path from recommend_actions_node, so no extra fields needed here."""
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

    async def _recommend_actions(state: CampaignState) -> CampaignState:
        return await recommend_actions_node(state, db)

    async def _apply_policy(state: CampaignState) -> CampaignState:
        return await apply_policy_node(state, db)

    async def _emit_audit(state: CampaignState) -> CampaignState:
        return await emit_audit_node(state, db)

    graph = StateGraph(CampaignState)
    graph.add_node("load_orders", _load_orders)
    graph.add_node("segment_customers", _segment_customers)
    graph.add_node("recommend_actions", _recommend_actions)
    graph.add_node("apply_policy", _apply_policy)
    graph.add_node("emit_audit", _emit_audit)

    graph.set_entry_point("load_orders")
    graph.add_edge("load_orders", "segment_customers")
    graph.add_edge("segment_customers", "recommend_actions")
    graph.add_edge("recommend_actions", "apply_policy")
    graph.add_edge("apply_policy", "emit_audit")
    graph.add_edge("emit_audit", END)

    return graph.compile()
