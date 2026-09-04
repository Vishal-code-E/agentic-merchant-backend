import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from langfuse import observe, propagate_attributes
from razorpay.errors import BadRequestError, GatewayError, ServerError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.checkout_graph import build_checkout_graph
from app.agents.state import CheckoutState
from app.config.settings import get_settings
from app.db.session import get_db
from app.models.agent_run import AgentRun
from app.models.product import Product
from app.observability.langfuse_client import get_langfuse_client, get_langfuse_handler
from app.schemas.checkout import (
    ChatCheckoutRequest,
    ChatCheckoutResponse,
    CheckoutRequest,
    CheckoutResponse,
)
from app.schemas.product import ProductResponse
from app.services.agent_auth import verify_agent_api_key
from app.services.audit_service import AuditService
from app.services.intent_parser import (
    IntentParserUnavailable,
    MessageTooLongError,
    detect_suspicious_pattern,
    parse_intent_to_cart,
    validate_message_length,
)
from app.services.rate_limiter import enforce_rate_limit

router = APIRouter(tags=["checkout"])
settings = get_settings()

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
    "idempotency_conflict": 409,
}

#: failure_stage values that mean "refused at the policy gate" rather than
#: "malformed request" — the moments get_db()'s rollback-on-exception would
#: otherwise silently erase the evidence for (see agent_checkout docstring).
#: policy_missing never reaches PolicyEngine.evaluate(), so check_policy_node
#: has no decision of its own to log for that stage.
POLICY_GATED_STAGES = {"policy", "policy_missing"}

langfuse = get_langfuse_client()


async def _run_checkout_graph(
    checkout_request: CheckoutRequest,
    idempotency_key: str,
    agent_run: AgentRun,
    db: AsyncSession,
) -> CheckoutResponse:
    """
    Shared by /agent/checkout and /agent/chat-checkout: builds CheckoutState,
    runs checkout_graph unmodified, and turns its result into a CheckoutResponse
    or an HTTPException. Caller has already created+committed agent_run and
    opened the Langfuse span/propagation context this rides inside of.
    """
    audit_service = AuditService(db)

    initial_state: CheckoutState = {
        "merchant_id": str(checkout_request.merchant_id),
        "customer_context": checkout_request.customer_context,
        "cart_items": [item.model_dump() for item in checkout_request.cart_items],
        "agent_run_id": str(agent_run.id),
        "idempotency_key": idempotency_key,
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


@router.post("/agent/checkout", response_model=CheckoutResponse)
@observe(capture_input=False, capture_output=False)
async def agent_checkout(
    payload: CheckoutRequest,
    x_agent_api_key: str | None = Header(default=None, alias="X-Agent-Api-Key"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_agent_name: str | None = Header(default=None, alias="X-Agent-Name"),
    x_agent_version: str | None = Header(default=None, alias="X-Agent-Version"),
    db: AsyncSession = Depends(get_db),
):
    """
    Accepts a structured cart request from an external AI agent, runs
    checkout_graph, returns order details + explanation.

    Two preconditions are checked before any tracing/AgentRun/graph work
    starts, and both reject with a plain HTTPException rather than FastAPI's
    default validation-error handling for a missing header (which would be a
    422, not the status callers should key retry logic off of here):

    - X-Agent-Api-Key must match this merchant's stored key (401) — see
      app/services/agent_auth.py.
    - Idempotency-Key must be present (400) — declared as an optional Header
      here specifically so its absence can be turned into a 400 instead of
      FastAPI's automatic 422. create_order_node uses it to detect a retried
      request and return the original order instead of creating a second one
      or calling Razorpay again (true idempotency, not just receipt-based
      hope — see that node's docstring).

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
    await verify_agent_api_key(payload.merchant_id, x_agent_api_key, db)
    await enforce_rate_limit("agent_checkout", x_agent_api_key)

    if not idempotency_key:
        raise HTTPException(
            status_code=400,
            detail=(
                "Missing required Idempotency-Key header. Supply a unique key per checkout "
                "attempt — retrying with the same key returns the original order instead of "
                "creating a duplicate."
            ),
        )

    request_id = str(uuid.uuid4())  # distinct from agent_run.id — identifies this HTTP call, not the graph run
    agent_name = x_agent_name or "unknown"
    agent_version = x_agent_version or "unknown"

    trace_id = langfuse.get_current_trace_id()
    customer_id = (payload.customer_context or {}).get("customer_id")

    trace_metadata = {
        "merchant_id": str(payload.merchant_id),
        "endpoint": "/agent/checkout",
        "agent_name": agent_name,
        "agent_version": agent_version,
        "request_id": request_id,
        "idempotency_key": idempotency_key,
    }

    propagation_kwargs: dict = {
        "trace_name": "agent-checkout",
        "tags": ["checkout"],
        "metadata": trace_metadata,
        "environment": settings.app_env,
    }
    if customer_id:
        propagation_kwargs["user_id"] = str(customer_id)
        propagation_kwargs["session_id"] = str(customer_id)

    with propagate_attributes(**propagation_kwargs):
        # get_current_trace_id() must be called inside propagate_attributes so
        # the OTel span is already active and the ID is non-None. Calling it
        # before entering the context (before the @observe span propagates in
        # async FastAPI) can return None, making AgentRun.langfuse_trace_id NULL.
        trace_id = langfuse.get_current_trace_id()
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
            agent_name=agent_name,
            agent_version=agent_version,
        )
        db.add(agent_run)
        await db.commit()

        result = await _run_checkout_graph(payload, idempotency_key, agent_run, db)
        # Flush promptly so spans aren't waiting in the OTel batch buffer.
        # In a long-running dev server, spans can sit for 30-60 s without this.
        await asyncio.to_thread(langfuse.flush)
        return result


@router.post("/agent/chat-checkout", response_model=ChatCheckoutResponse)
@observe(capture_input=False, capture_output=False)
async def agent_chat_checkout(
    payload: ChatCheckoutRequest,
    x_agent_api_key: str | None = Header(default=None, alias="X-Agent-Api-Key"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    x_agent_name: str | None = Header(default=None, alias="X-Agent-Name"),
    x_agent_version: str | None = Header(default=None, alias="X-Agent-Version"),
    db: AsyncSession = Depends(get_db),
):
    """
    Conversational checkout: turns a free-text shopper message into a cart via
    intent_parser.parse_intent_to_cart (LLM call, constrained to this
    merchant's real catalog), then runs the resulting CheckoutRequest through
    the exact same checkout_graph path as /agent/checkout — same
    ValidateCart/SuggestUpsell/CheckPolicy/CreateOrder/Finalize, same
    checkout_denied auditing, via the shared _run_checkout_graph() helper.

    Idempotency-Key is optional here, unlike /agent/checkout: a chat message
    has no natural place to carry that header. When absent, one is generated
    per call — meaning retrying the same message without an explicit key is
    NOT idempotent and can create a second order. A caller that wants
    replay-safety should pass its own Idempotency-Key, same contract as
    /agent/checkout.

    A "no confident match" result (matched=false) is a normal, successful
    response (HTTP 200) — the shopper asked for something this catalog can't
    satisfy, not a server error.
    """
    await verify_agent_api_key(payload.merchant_id, x_agent_api_key, db)
    await enforce_rate_limit("agent_chat_checkout", x_agent_api_key)

    try:
        validate_message_length(payload.message)
    except MessageTooLongError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    request_id = str(uuid.uuid4())  # distinct from agent_run.id — identifies this HTTP call, not the graph run
    agent_name = x_agent_name or "unknown"
    agent_version = x_agent_version or "unknown"
    customer_id = (payload.customer_context or {}).get("customer_id")

    trace_metadata = {
        "merchant_id": str(payload.merchant_id),
        "endpoint": "/agent/chat-checkout",
        "agent_name": agent_name,
        "agent_version": agent_version,
        "request_id": request_id,
    }
    if idempotency_key:
        trace_metadata["idempotency_key"] = idempotency_key

    # tags include "chat" so this trace is identifiable as chat-originated,
    # distinct from a structured /agent/checkout call.
    propagation_kwargs: dict = {
        "trace_name": "chat-checkout",
        "tags": ["checkout", "chat"],
        "metadata": trace_metadata,
        "environment": settings.app_env,
    }
    if customer_id:
        propagation_kwargs["user_id"] = str(customer_id)
        propagation_kwargs["session_id"] = str(customer_id)

    with propagate_attributes(**propagation_kwargs):
        # get_current_trace_id() inside propagate_attributes — see agent_checkout's
        # identical comment for why this ordering matters.
        from app.services.data_sanitizer import sanitize_string
        trace_id = langfuse.get_current_trace_id()
        langfuse.update_current_span(
            input={"merchant_id": str(payload.merchant_id), "message": sanitize_string(payload.message)}
        )

        agent_run = AgentRun(
            id=uuid.uuid4(),
            merchant_id=payload.merchant_id,
            type="checkout",
            status="running",
            langfuse_trace_id=trace_id,
            started_at=datetime.now(timezone.utc),
            agent_name=agent_name,
            agent_version=agent_version,
        )
        db.add(agent_run)
        await db.commit()

        # Detection, not blocking (see intent_parser.detect_suspicious_pattern's
        # docstring) — audited BEFORE the LLM call below, whatever the outcome.
        suspicious_pattern = detect_suspicious_pattern(payload.message)
        suspicious_metadata = {"suspicious_input": bool(suspicious_pattern)}
        if suspicious_pattern:
            suspicious_metadata["suspicious_pattern"] = suspicious_pattern
        langfuse.update_current_span(metadata=suspicious_metadata)
        if suspicious_pattern:
            await AuditService(db).log_event(
                agent_run_id=str(agent_run.id),
                event_type="suspicious_input_detected",
                payload={"pattern": suspicious_pattern, "message": payload.message},
            )

        catalog_result = await db.execute(
            select(Product).where(Product.merchant_id == payload.merchant_id, Product.stock > 0)
        )
        catalog = catalog_result.scalars().all()

        try:
            checkout_request, interpretation = await parse_intent_to_cart(
                payload.message, catalog, str(payload.merchant_id)
            )
        except IntentParserUnavailable as e:
            agent_run.status = "failed"
            agent_run.ended_at = datetime.now(timezone.utc)
            await db.commit()
            langfuse.update_current_span(output={"status": "failed", "error": str(e)})
            await asyncio.to_thread(langfuse.flush)
            raise HTTPException(status_code=503, detail=str(e)) from e
        except Exception as e:
            # Anything else (provider rate limit, network blip, malformed
            # response) must still terminate agent_run — otherwise it's stuck
            # at status="running" forever, same reasoning as _run_checkout_graph's
            # RAZORPAY_ERRORS handling above.
            agent_run.status = "failed"
            agent_run.ended_at = datetime.now(timezone.utc)
            await db.commit()
            langfuse.update_current_span(output={"status": "failed", "error": str(e)})
            await asyncio.to_thread(langfuse.flush)
            raise HTTPException(
                status_code=502, detail="The conversational-checkout model is temporarily unavailable."
            ) from e

        # Explainability: log the translation step itself, before the
        # checkout_graph result (if any) is known — committed immediately since
        # get_db() rolls back the whole session on any later exception.
        await AuditService(db).log_event(
            agent_run_id=str(agent_run.id),
            event_type="intent_parsed",
            payload={"message": payload.message, "interpretation": interpretation},
        )
        await db.commit()

        if checkout_request is None:
            agent_run.status = "success"
            agent_run.ended_at = datetime.now(timezone.utc)
            await db.commit()
            langfuse.update_current_span(output={"matched": False, "interpretation": interpretation})
            await asyncio.to_thread(langfuse.flush)
            return ChatCheckoutResponse(interpretation=interpretation, checkout_result=None, matched=False)

        checkout_request.customer_context = payload.customer_context
        effective_idempotency_key = idempotency_key or str(uuid.uuid4())

        checkout_result = await _run_checkout_graph(
            checkout_request, effective_idempotency_key, agent_run, db
        )
        await asyncio.to_thread(langfuse.flush)
        return ChatCheckoutResponse(interpretation=interpretation, checkout_result=checkout_result, matched=True)

