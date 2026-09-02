"""
campaign_graph: LoadOrders -> SegmentCustomers -> RecommendActions -> ApplyPolicies -> EmitEvents

Background revenue workflow, run via a Celery/worker task (see app/workers/tasks.py).
v1 scope: log-only — recommend and record actions, don't yet auto-trigger campaigns.
"""
from app.agents.state import CampaignState


async def load_orders_node(state: CampaignState) -> CampaignState:
    """Query DB for orders in the given time window. TODO(v1.3)."""
    raise NotImplementedError


async def segment_customers_node(state: CampaignState) -> CampaignState:
    """Classify customers (high-value, dormant, recent-failure) via simple rules. TODO(v1.3)."""
    raise NotImplementedError


async def recommend_actions_node(state: CampaignState) -> CampaignState:
    """Propose campaigns (rules or LLM-based reasoning). TODO(v1.3)."""
    raise NotImplementedError


async def apply_policies_node(state: CampaignState) -> CampaignState:
    """Ensure proposed campaigns respect merchant policy limits. TODO(v1.3)."""
    raise NotImplementedError


async def emit_events_node(state: CampaignState) -> CampaignState:
    """Log recommended actions to DB/audit; optionally enqueue notification tasks. TODO(v1.3)."""
    raise NotImplementedError


def build_campaign_graph():
    """TODO(v1.3): wire nodes into a langgraph.graph.StateGraph(CampaignState)."""
    raise NotImplementedError
