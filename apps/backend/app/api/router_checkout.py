import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from langfuse import observe, propagate_attributes
from razorpay.errors import BadRequestError, GatewayError, ServerError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.checkout_graph import build_checkout_graph
from app.agents.state import CheckoutState
from app.db.session import get_db
from app.models.agent_run import AgentRun
from app.observability.langfuse_client import get_langfuse_client, get_langfuse_handler
from app.schemas.checkout import CheckoutRequest, CheckoutResponse
from app.schemas.product import ProductResponse
from app.services.audit_service import AuditService

router = APIRouter(tags=["checkout"])

RAZORPAY_ERRORS = (BadRequestError, GatewayError, ServerError)

#: CheckoutState.failure_stage -> HTTP status. A policy denial is a refusal to
#: act on a well-formed request (403); a cart problem is a malformed request
#: (400); a merchant with no policy row is a server-side data defect the caller
#: cannot fix by retrying (409).
FAILURE_STAGE_STATUS = {
    "validate_cart": 400,
    "policy": 403,
    "policy_missing": 409,
    "create_order": 400,
}

#: failure_stage values that mean "refused at the policy gate" rather than
#: "malformed request" — the moments get_db()'s rollback-on-exception would
#: otherwise silently erase the evidence for (see agent_checkout docstring).
#: policy_missing never reaches PolicyEngine.evaluate(), so check_policy_node
#: has no decision of its own to log for that stage.
POLICY_GATED_STAGES = {"policy", "policy_missing"}

langfuse = get_langfuse_client()


@router.post("/agent/checkout", response_model=CheckoutResponse)
@observe(capture_input=False, capture_output=False)
async def agent_checkout(payload: CheckoutRequest, db: AsyncSession = Depends(get_db)):
    """
    Accepts a structured cart request from an external AI agent, runs
    checkout_graph, returns order details + explanation.

    capture_input/output are disabled on @observe() and set explicitly below
    instead — the default would otherwise dump every function arg, including
    the raw AsyncSession, as trace input (see Langfuse's "Common Mistakes":
    not explicitly setting @observe input/output).

    Every call gets an AgentRun row, with AgentRun.langfuse_trace_id set to
    the real Langfuse trace id (not a locally-invented label) so an AgentRun
    row and its Langfuse trace can be looked up from each other. A
    policy-gated denial also gets a checkout_denied audit_logs row. Both are
    committed explicitly before any HTTPException is raised: get_db() rolls
    back the whole session on any exception it sees, HTTPException included,
    so an uncommitted audit write "before raising" would otherwise be the
    first thing discarded (see router_onboarding.py's own docstring on this
    exact get_db() behavior).

    session_id/user_id are only set when the caller supplies a
    customer_context.customer_id: Langfuse's own best-practices guidance is
    that a session groups multiple *related* traces, and a single checkout
    call has nothing to group with unless we know which customer it's for.
    """
    trace_id = langfuse.get_current_trace_id()
    customer_id = (payload.customer_context or {}).get("customer_id")

    propagation_kwargs: dict = {"trace_name": "agent-checkout", "tags": ["checkout"]}
    if customer_id:
        propagation_kwargs["user_id"] = str(customer_id)
        propagation_kwargs["session_id"] = str(customer_id)

    with propagate_attributes(**propagation_kwargs):
        langfuse.update_current_span(
            input={
                "merchant_id": str(payload.merchant_id),
                "cart_items": [item.model_dump(by_alias=True) for item in payload.cart_items],
            }
        )

        agent_run = AgentRun(
            id=uuid.uuid4(),
            merchant_id=payload.merchant_id,
            type="checkout",
            status="running",
            langfuse_trace_id=trace_id,
            started_at=datetime.now(timezone.utc),
        )
        db.add(agent_run)
        await db.commit()

        audit_service = AuditService(db)

        initial_state: CheckoutState = {
            "merchant_id": str(payload.merchant_id),
            "customer_context": payload.customer_context,
            "cart_items": [item.model_dump() for item in payload.cart_items],
            "agent_run_id": str(agent_run.id),
        }

        graph = build_checkout_graph(db)
        # run_name replaces the generic "LangGraph" label the callback handler
        # would otherwise give this span (see Langfuse's LangGraph cookbook).
        graph_config = {"callbacks": [get_langfuse_handler()], "run_name": "checkout-graph"}

        try:
            result: CheckoutState = await graph.ainvoke(initial_state, config=graph_config)
        except RAZORPAY_ERRORS as e:
            agent_run.status = "failed"
            agent_run.ended_at = datetime.now(timezone.utc)
            await db.commit()
            langfuse.update_current_span(output={"status": "failed", "error": str(e)})
            raise HTTPException(status_code=502, detail=f"Razorpay error: {e}") from e

        if result.get("status") == "failed":
            failure_stage = result.get("failure_stage")
            status_code = FAILURE_STAGE_STATUS.get(failure_stage, 400)

            if failure_stage in POLICY_GATED_STAGES:
                await audit_service.log_event(
                    agent_run_id=str(agent_run.id),
                    event_type="checkout_denied",
                    payload={
                        "failure_stage": failure_stage,
                        "explanation": result.get("explanation"),
                        "policy_result": result.get("policy_result"),
                    },
                )

            agent_run.status = "failed"
            agent_run.ended_at = datetime.now(timezone.utc)
            await db.commit()

            langfuse.update_current_span(
                output={
                    "status": "failed",
                    "failure_stage": failure_stage,
                    "explanation": result.get("explanation"),
                }
            )
            raise HTTPException(
                status_code=status_code,
                detail=result.get("explanation") or "Checkout validation failed.",
            )

        agent_run.status = "success"
        agent_run.ended_at = datetime.now(timezone.utc)
        await db.commit()

        langfuse.update_current_span(
            output={
                "status": "success",
                "razorpay_order_id": result.get("razorpay_order_id"),
                "amount": result.get("amount"),
                "currency": result.get("currency"),
            }
        )

        return CheckoutResponse(
            status=result["status"],
            razorpay_order_id=result.get("razorpay_order_id"),
            amount=result.get("amount") or 0.0,
            currency=result.get("currency") or "INR",
            upsell_suggestions=[
                ProductResponse.model_validate(item)
                for item in result.get("upsell_suggestions") or []
            ],
            explanation=result.get("explanation") or "",
        )
