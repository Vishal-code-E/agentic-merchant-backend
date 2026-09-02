from fastapi import APIRouter

router = APIRouter(tags=["checkout"])


@router.post("/agent/checkout")
async def agent_checkout():
    """
    Accepts a structured cart request from an external AI agent, runs
    checkout_graph, returns order details + explanation. TODO(v1.1/v1.2).
    """
    raise NotImplementedError
