from fastapi import APIRouter, Depends, HTTPException
from razorpay.errors import BadRequestError, GatewayError, ServerError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.checkout_graph import build_checkout_graph
from app.agents.state import CheckoutState
from app.db.session import get_db
from app.schemas.checkout import CheckoutRequest, CheckoutResponse

router = APIRouter(tags=["checkout"])

RAZORPAY_ERRORS = (BadRequestError, GatewayError, ServerError)


@router.post("/agent/checkout", response_model=CheckoutResponse)
async def agent_checkout(payload: CheckoutRequest, db: AsyncSession = Depends(get_db)):
    """
    Accepts a structured cart request from an external AI agent, runs
    checkout_graph, returns order details + explanation.
    """
    initial_state: CheckoutState = {
        "merchant_id": str(payload.merchant_id),
        "customer_context": payload.customer_context,
        "cart_items": [item.model_dump() for item in payload.cart_items],
    }

    graph = build_checkout_graph(db)

    try:
        result: CheckoutState = await graph.ainvoke(initial_state)
    except RAZORPAY_ERRORS as e:
        raise HTTPException(status_code=502, detail=f"Razorpay error: {e}") from e

    if result.get("status") == "failed":
        raise HTTPException(status_code=400, detail=result.get("explanation") or "Checkout validation failed.")

    return CheckoutResponse(
        status=result["status"],
        razorpay_order_id=result.get("razorpay_order_id"),
        amount=result.get("amount") or 0.0,
        currency=result.get("currency") or "INR",
        upsell_suggestions=[],
        explanation=result.get("explanation") or "",
    )
