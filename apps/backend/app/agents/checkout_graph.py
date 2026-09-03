"""
checkout_graph: Input -> ValidateCart -> SuggestUpsell -> CheckPolicy -> CreateOrder -> Finalize

v1.1 target: Input -> ValidateCart -> CreateOrder -> Finalize (no upsell, no policy).
v1.2+: wire in SuggestUpsellNode and CheckPolicyNode (see Graph Engineering doc §7).

Nodes are deterministic control flow; only SuggestUpsellNode may use an LLM,
and only for suggestion, never for the policy/payment decision itself.
"""
import uuid

from langgraph.graph import END, StateGraph
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.state import CheckoutState
from app.models.merchant import Merchant
from app.models.order import Order
from app.models.product import Product
from app.services.encryption import decrypt_secret
from app.services.razorpay_client import RazorpayClient


async def input_node(state: CheckoutState) -> CheckoutState:
    """Fill in CheckoutState defaults around the router-supplied request fields."""
    state.setdefault("customer_context", None)
    state.setdefault("constraints", {})
    state.setdefault("upsell_suggestions", None)
    state.setdefault("policy_result", None)
    state.setdefault("order_id", None)
    state.setdefault("razorpay_order_id", None)
    state.setdefault("amount", None)
    state.setdefault("currency", None)
    state["status"] = "pending"
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
        state["explanation"] = "Cart is empty."
        return state

    canonical_items: list[dict] = []
    currency: str | None = None

    for raw in raw_items:
        product_id = str(raw["product_id"])
        quantity = raw["quantity"]

        if quantity <= 0:
            state["status"] = "failed"
            state["explanation"] = f"Invalid quantity for product {product_id}."
            return state

        product = await db.get(Product, uuid.UUID(product_id))
        if product is None or str(product.merchant_id) != merchant_id:
            state["status"] = "failed"
            state["explanation"] = f"Product {product_id} not found for this merchant."
            return state

        if product.stock < quantity:
            state["status"] = "failed"
            state["explanation"] = f"Insufficient stock for product '{product.name}'."
            return state

        if currency is None:
            currency = product.currency
        elif currency != product.currency:
            state["status"] = "failed"
            state["explanation"] = "Cart items must share a single currency."
            return state

        canonical_items.append(
            {
                "product_id": str(product.id),
                "name": product.name,
                "quantity": quantity,
                "unit_price": float(product.price),
                "currency": product.currency,
            }
        )

    state["cart_items"] = canonical_items
    state["currency"] = currency
    state["amount"] = sum(item["unit_price"] * item["quantity"] for item in canonical_items)
    return state


async def suggest_upsell_node(state: CheckoutState) -> CheckoutState:
    """Propose upsell/cross-sell items via heuristics or LLM. TODO(v1.2)."""
    raise NotImplementedError


async def check_policy_node(state: CheckoutState) -> CheckoutState:
    """Call policy_engine.evaluate(); set policy_result. TODO(v1.2)."""
    raise NotImplementedError


async def create_order_node(state: CheckoutState, db: AsyncSession) -> CheckoutState:
    """
    Create a local Order row, then call RazorpayClient.create_order() using the
    Order's own id as the receipt (idempotency key). Razorpay SDK errors are
    left to propagate so the router can map them to a 502.
    """
    merchant = await db.get(Merchant, uuid.UUID(state["merchant_id"]))
    if merchant is None:
        state["status"] = "failed"
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

    client = RazorpayClient(merchant.razorpay_key_id, decrypt_secret(merchant.razorpay_key_secret))
    amount_paise = int(round(amount * 100))

    razorpay_order = await client.create_order(
        amount_paise=amount_paise,
        currency=currency,
        receipt=str(order.id),
        notes={"merchant_id": str(merchant.id), "order_id": str(order.id)},
    )

    order.razorpay_order_id = razorpay_order["id"]
    order.status = "success"
    await db.flush()

    state["order_id"] = str(order.id)
    state["razorpay_order_id"] = order.razorpay_order_id
    state["status"] = "success"
    return state


async def finalize_node(state: CheckoutState) -> CheckoutState:
    """Build the final explanation string. Response assembly happens in the router."""
    if state.get("status") == "failed":
        state.setdefault("explanation", "Checkout failed.")
        return state

    item_count = len(state.get("cart_items", []))
    state["explanation"] = (
        f"Order created successfully for {item_count} item(s), "
        f"total {state.get('amount')} {state.get('currency')}."
    )
    return state


def _route_after_validate(state: CheckoutState) -> str:
    return "finalize" if state.get("status") == "failed" else "create_order"


def build_checkout_graph(db: AsyncSession):
    """
    Wire the v1.1 minimal path: Input -> ValidateCart -> CreateOrder -> Finalize,
    short-circuiting straight to Finalize if ValidateCart fails. SuggestUpsellNode
    and CheckPolicyNode stay unwired until v1.2.
    """

    async def _validate_cart(state: CheckoutState) -> CheckoutState:
        return await validate_cart_node(state, db)

    async def _create_order(state: CheckoutState) -> CheckoutState:
        return await create_order_node(state, db)

    graph = StateGraph(CheckoutState)
    graph.add_node("input", input_node)
    graph.add_node("validate_cart", _validate_cart)
    graph.add_node("create_order", _create_order)
    graph.add_node("finalize", finalize_node)

    graph.set_entry_point("input")
    graph.add_edge("input", "validate_cart")
    graph.add_conditional_edges(
        "validate_cart",
        _route_after_validate,
        {"create_order": "create_order", "finalize": "finalize"},
    )
    graph.add_edge("create_order", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile()
