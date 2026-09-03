"""
checkout_graph: Input -> ValidateCart -> SuggestUpsell -> CheckPolicy -> CreateOrder -> Finalize

Nodes are deterministic control flow; only SuggestUpsellNode may use an LLM,
and only for suggestion, never for the policy/payment decision itself.

v1.2 wires in SuggestUpsellNode and CheckPolicyNode (see Graph Engineering doc §7).
SuggestUpsell is deliberately heuristic-only for now — no LLM call.
"""
import uuid

from langgraph.graph import END, StateGraph
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.state import CheckoutState
from app.models.merchant import Merchant
from app.models.order import Order
from app.models.policy import Policy
from app.models.product import Product
from app.services.audit_service import AuditService
from app.services.encryption import decrypt_secret
from app.services.policy_engine import PolicyEngine, cart_total
from app.services.razorpay_client import RazorpayClient

#: Total upsell suggestions returned per checkout, across all cart categories.
UPSELL_MAX_SUGGESTIONS = 3


async def input_node(state: CheckoutState) -> CheckoutState:
    """Fill in CheckoutState defaults around the router-supplied request fields."""
    state.setdefault("customer_context", None)
    state.setdefault("constraints", {})
    state.setdefault("agent_run_id", None)
    state.setdefault("upsell_suggestions", None)
    state.setdefault("policy_result", None)
    state.setdefault("order_id", None)
    state.setdefault("razorpay_order_id", None)
    state.setdefault("amount", None)
    state.setdefault("currency", None)
    state["status"] = "pending"
    state.setdefault("failure_stage", None)
    state.setdefault("explanation", None)
    return state


async def validate_cart_node(state: CheckoutState, db: AsyncSession) -> CheckoutState:
    """
    Look up each cart item's product_id in the DB, confirm it exists, is in
    stock, and belongs to the requesting merchant. Computes canonical
    cart_items with real DB prices — client-supplied prices are never trusted
    (the request schema doesn't even carry a price field).
    """
    merchant_id = state["merchant_id"]
    raw_items = state.get("cart_items") or []

    if not raw_items:
        state["status"] = "failed"
        state["failure_stage"] = "validate_cart"
        state["explanation"] = "Cart is empty."
        return state

    canonical_items: list[dict] = []
    currency: str | None = None

    for raw in raw_items:
        product_id = str(raw["product_id"])
        quantity = raw["quantity"]

        if quantity <= 0:
            state["status"] = "failed"
            state["failure_stage"] = "validate_cart"
            state["explanation"] = f"Invalid quantity for product {product_id}."
            return state

        product = await db.get(Product, uuid.UUID(product_id))
        if product is None or str(product.merchant_id) != merchant_id:
            state["status"] = "failed"
            state["failure_stage"] = "validate_cart"
            state["explanation"] = f"Product {product_id} not found for this merchant."
            return state

        if product.stock < quantity:
            state["status"] = "failed"
            state["failure_stage"] = "validate_cart"
            state["explanation"] = f"Insufficient stock for product '{product.name}'."
            return state

        if currency is None:
            currency = product.currency
        elif currency != product.currency:
            state["status"] = "failed"
            state["failure_stage"] = "validate_cart"
            state["explanation"] = "Cart items must share a single currency."
            return state

        canonical_items.append(
            {
                "product_id": str(product.id),
                "name": product.name,
                # Needed by check_policy_node (allowed_categories) and by
                # suggest_upsell_node (which categories to search).
                "category": product.category,
                "quantity": quantity,
                "unit_price": float(product.price),
                "currency": product.currency,
            }
        )

    state["cart_items"] = canonical_items
    state["currency"] = currency
    state["amount"] = sum(item["unit_price"] * item["quantity"] for item in canonical_items)
    return state


async def suggest_upsell_node(state: CheckoutState, db: AsyncSession) -> CheckoutState:
    """
    Heuristic cross-sell: for each distinct category already in the cart, pull the
    cheapest in-stock products from the same merchant that aren't already in the
    cart, then keep the globally cheapest UPSELL_MAX_SUGGESTIONS across all
    categories (not per category).

    No LLM. Cheapest-first is chosen so an upsell is unlikely to breach
    max_amount; check_policy_node filters whatever still would.

    This node never fails the checkout — worst case it suggests nothing.
    """
    cart_items = state.get("cart_items") or []
    state["upsell_suggestions"] = []
    if not cart_items:
        return state

    merchant_uuid = uuid.UUID(state["merchant_id"])
    cart_product_ids = [uuid.UUID(item["product_id"]) for item in cart_items]
    # dict.fromkeys preserves cart order and de-duplicates; drop uncategorised items.
    categories = [c for c in dict.fromkeys(item.get("category") for item in cart_items) if c]
    if not categories:
        return state

    # Keyed by product id so a product matching two cart categories isn't suggested twice.
    candidates: dict[str, dict] = {}
    for category in categories:
        result = await db.execute(
            select(Product)
            .where(
                Product.merchant_id == merchant_uuid,
                Product.category == category,
                Product.stock > 0,
                Product.id.notin_(cart_product_ids),
            )
            .order_by(Product.price.asc())
            .limit(UPSELL_MAX_SUGGESTIONS)
        )
        for product in result.scalars().all():
            candidates[str(product.id)] = {
                "id": str(product.id),
                "merchant_id": str(product.merchant_id),
                "name": product.name,
                "description": product.description,
                "price": float(product.price),
                "currency": product.currency,
                "category": product.category,
                "tags": list(product.tags or []),
                "stock": product.stock,
            }

    state["upsell_suggestions"] = sorted(candidates.values(), key=lambda p: p["price"])[
        :UPSELL_MAX_SUGGESTIONS
    ]
    return state


async def check_policy_node(state: CheckoutState, db: AsyncSession) -> CheckoutState:
    """
    The gate before payment. Loads the merchant's Policy, filters any upsell
    suggestion that would breach it, then judges the customer's cart.

    Fails closed if no Policy row exists. From v1.2 onward that is impossible
    for newly onboarded merchants (router_onboarding writes both rows in one
    transaction), but merchants created before this change have no policy and
    must be denied clearly rather than crashing or silently passing.
    """
    result = await db.execute(
        select(Policy).where(Policy.merchant_id == uuid.UUID(state["merchant_id"])).limit(1)
    )
    policy_row = result.scalars().first()

    if policy_row is None:
        state["status"] = "failed"
        state["failure_stage"] = "policy_missing"
        state["explanation"] = (
            "Merchant has no policy configured; refusing to authorise payment. "
            "Configure one via PATCH /merchant/{merchant_id}/policy."
        )
        state["policy_result"] = {
            "allowed": False,
            "reason": "No policy row exists for this merchant.",
            "notes": [],
        }
        # Suggestions can't be policy-checked without a policy — withhold them.
        state["upsell_suggestions"] = []
        return state

    policy = {
        "max_amount": policy_row.max_amount,
        "allowed_categories": list(policy_row.allowed_categories or []),
        "per_user_limit": policy_row.per_user_limit,
    }

    engine = PolicyEngine()
    cart_items = state.get("cart_items") or []

    kept_upsells, upsell_notes = engine.filter_upsells(
        cart_items, state.get("upsell_suggestions") or [], policy
    )
    state["upsell_suggestions"] = kept_upsells

    decision = engine.evaluate(cart_items, policy, state.get("customer_context"))
    state["policy_result"] = {
        "allowed": decision.allowed,
        "reason": decision.reason,
        "notes": decision.notes + upsell_notes,
    }

    # Evidence for the gate itself, independent of allow/deny — logged every
    # time evaluate() actually runs (the policy_missing early-return above
    # never reaches here; router_checkout writes its own audit row for that
    # case instead, since there's no PolicyEngine decision to report).
    audit_payload = {
        "cart_total": cart_total(cart_items),
        "policy_id": str(policy_row.id),
        # policy["max_amount"] is a Decimal off the ORM column — JSONB storage
        # (via asyncpg's json.dumps-based codec) can't serialize Decimal.
        "max_amount": float(policy["max_amount"]) if policy["max_amount"] is not None else None,
        "allowed_categories": policy["allowed_categories"],
        "decision": decision.allowed,
        "reason": decision.reason,
    }
    if policy["per_user_limit"] is not None:
        audit_payload["per_user_limit_check"] = "best_effort_no_ledger"

    await AuditService(db).log_event(
        agent_run_id=state.get("agent_run_id"),
        event_type="policy_check",
        payload=audit_payload,
    )

    if not decision.allowed:
        state["status"] = "failed"
        state["failure_stage"] = "policy"
        state["explanation"] = decision.reason or "Checkout denied by merchant policy."

    return state


async def create_order_node(state: CheckoutState, db: AsyncSession) -> CheckoutState:
    """
    Create a local Order row, then call RazorpayClient.create_order() using the
    Order's own id as the receipt (idempotency key). Razorpay SDK errors are
    left to propagate so the router can map them to a 502 — but are audited
    (event_type="razorpay_order_failed") before they're re-raised.
    """
    merchant = await db.get(Merchant, uuid.UUID(state["merchant_id"]))
    if merchant is None:
        state["status"] = "failed"
        state["failure_stage"] = "create_order"
        state["explanation"] = "Merchant not found."
        return state

    amount = state.get("amount") or 0.0
    currency = state.get("currency") or "INR"

    order = Order(
        merchant_id=merchant.id,
        status="pending",
        amount=amount,
        currency=currency,
        cart_snapshot={"items": state.get("cart_items", [])},
    )
    db.add(order)
    await db.flush()
    await db.refresh(order)

    audit_service = AuditService(db)
    client = RazorpayClient(merchant.razorpay_key_id, decrypt_secret(merchant.razorpay_key_secret))
    amount_paise = int(round(amount * 100))

    try:
        razorpay_order = await client.create_order(
            amount_paise=amount_paise,
            currency=currency,
            receipt=str(order.id),
            notes={"merchant_id": str(merchant.id), "order_id": str(order.id)},
        )
    except Exception as e:
        order.status = "failed"
        await db.flush()
        await audit_service.log_event(
            agent_run_id=state.get("agent_run_id"),
            event_type="razorpay_order_failed",
            payload={
                "order_id": str(order.id),
                "amount": amount,
                "currency": currency,
                "error": str(e),
            },
        )
        raise

    order.razorpay_order_id = razorpay_order["id"]
    order.status = "success"
    await db.flush()

    await audit_service.log_event(
        agent_run_id=state.get("agent_run_id"),
        event_type="razorpay_order_created",
        payload={
            "order_id": str(order.id),
            "razorpay_order_id": order.razorpay_order_id,
            "amount": amount,
            "currency": currency,
        },
    )

    state["order_id"] = str(order.id)
    state["razorpay_order_id"] = order.razorpay_order_id
    state["status"] = "success"
    return state


async def finalize_node(state: CheckoutState) -> CheckoutState:
    """
    Build the final explanation string. Response assembly happens in the router,
    which reads upsell_suggestions straight off the state.
    """
    state.setdefault("upsell_suggestions", [])

    if state.get("status") == "failed":
        policy_result = state.get("policy_result") or {}
        if state.get("failure_stage") in ("policy", "policy_missing"):
            # Surface the engine's own reason verbatim — it names the rule that
            # tripped, which is what an agent caller needs to correct the cart.
            state["explanation"] = (
                state.get("explanation")
                or policy_result.get("reason")
                or "Checkout denied by merchant policy."
            )
        elif not state.get("explanation"):
            state["explanation"] = "Checkout failed."
        return state

    item_count = len(state.get("cart_items", []))
    explanation = (
        f"Order created successfully for {item_count} item(s), "
        f"total {state.get('amount')} {state.get('currency')}."
    )

    upsell_count = len(state.get("upsell_suggestions") or [])
    if upsell_count:
        explanation += f" {upsell_count} policy-compliant upsell suggestion(s) included."

    state["explanation"] = explanation
    return state


def _route_after_validate(state: CheckoutState) -> str:
    return "finalize" if state.get("status") == "failed" else "suggest_upsell"


def _route_after_policy(state: CheckoutState) -> str:
    return "finalize" if state.get("status") == "failed" else "create_order"


def build_checkout_graph(db: AsyncSession):
    """
    Wire the v1.2 path:

        Input -> ValidateCart -> SuggestUpsell -> CheckPolicy -> CreateOrder -> Finalize

    Each check short-circuits straight to Finalize on failure. SuggestUpsell has
    no failure edge — it only ever adds suggestions, and CheckPolicy runs after
    it so no suggestion escapes the gate.
    """

    async def _validate_cart(state: CheckoutState) -> CheckoutState:
        return await validate_cart_node(state, db)

    async def _suggest_upsell(state: CheckoutState) -> CheckoutState:
        return await suggest_upsell_node(state, db)

    async def _check_policy(state: CheckoutState) -> CheckoutState:
        return await check_policy_node(state, db)

    async def _create_order(state: CheckoutState) -> CheckoutState:
        return await create_order_node(state, db)

    graph = StateGraph(CheckoutState)
    graph.add_node("input", input_node)
    graph.add_node("validate_cart", _validate_cart)
    graph.add_node("suggest_upsell", _suggest_upsell)
    graph.add_node("check_policy", _check_policy)
    graph.add_node("create_order", _create_order)
    graph.add_node("finalize", finalize_node)

    graph.set_entry_point("input")
    graph.add_edge("input", "validate_cart")
    graph.add_conditional_edges(
        "validate_cart",
        _route_after_validate,
        {"suggest_upsell": "suggest_upsell", "finalize": "finalize"},
    )
    graph.add_edge("suggest_upsell", "check_policy")
    graph.add_conditional_edges(
        "check_policy",
        _route_after_policy,
        {"create_order": "create_order", "finalize": "finalize"},
    )
    graph.add_edge("create_order", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()
