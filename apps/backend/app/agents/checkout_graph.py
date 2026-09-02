"""
checkout_graph: Input -> ValidateCart -> SuggestUpsell -> CheckPolicy -> CreateOrder -> Finalize

v1.0 target: Input -> ValidateCart -> CreateOrder -> Finalize (no upsell, minimal policy).
v1.1+: add SuggestUpsellNode and CheckPolicyNode (see Graph Engineering doc §7).

Nodes are deterministic control flow; only SuggestUpsellNode may use an LLM,
and only for suggestion, never for the policy/payment decision itself.
"""
from app.agents.state import CheckoutState


async def input_node(state: CheckoutState) -> CheckoutState:
    """Initialize CheckoutState from the incoming HTTP request. TODO(v1.0)."""
    raise NotImplementedError


async def validate_cart_node(state: CheckoutState) -> CheckoutState:
    """Look up products in catalog, populate canonical cart_items. TODO(v1.0)."""
    raise NotImplementedError


async def suggest_upsell_node(state: CheckoutState) -> CheckoutState:
    """Propose upsell/cross-sell items via heuristics or LLM. TODO(v1.1)."""
    raise NotImplementedError


async def check_policy_node(state: CheckoutState) -> CheckoutState:
    """Call policy_engine.evaluate(); set policy_result. TODO(v1.2)."""
    raise NotImplementedError


async def create_order_node(state: CheckoutState) -> CheckoutState:
    """Call razorpay_client.create_order() in test mode. TODO(v1.0)."""
    raise NotImplementedError


async def finalize_node(state: CheckoutState) -> CheckoutState:
    """Build the final response payload + explanation string. TODO(v1.0)."""
    raise NotImplementedError


def build_checkout_graph():
    """
    TODO(v1.0): wire the above nodes into a langgraph.graph.StateGraph(CheckoutState),
    with a Postgres checkpointer for state persistence (see LLD §4.1).
    """
    raise NotImplementedError
