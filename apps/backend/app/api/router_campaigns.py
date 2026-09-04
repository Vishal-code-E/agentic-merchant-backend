import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from langfuse import observe, propagate_attributes
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.campaign_graph import build_campaign_graph
from app.agents.state import CampaignState
from app.config.settings import get_settings
from app.db.session import get_db
from app.models.agent_run import AgentRun
from app.observability.langfuse_client import get_langfuse_client, get_langfuse_handler
from app.schemas.campaign import CampaignActionResult, CampaignRunRequest, CampaignRunResponse

router = APIRouter(tags=["campaigns"])

langfuse = get_langfuse_client()
settings = get_settings()


@router.post("/internal/campaigns/run", response_model=CampaignRunResponse)
@observe(capture_input=False, capture_output=False)
async def run_campaign(payload: CampaignRunRequest, db: AsyncSession = Depends(get_db)):
    """
    Manual trigger for campaign_graph. No scheduler yet — Celery Beat is an
    explicit fast-follow, not part of v1.3.

    capture_input is disabled and set explicitly below for the same reason as
    agent_checkout: the default would otherwise dump the raw AsyncSession
    argument into the trace input.

    No session_id here: each run is a one-shot, self-contained unit of work,
    not one of several related traces (unlike a multi-turn conversation),
    so there's nothing for a Langfuse session to group.
    """
    request_id = str(uuid.uuid4())  # distinct from agent_run.id — see router_checkout.py's identical convention
    trace_metadata = {
        "merchant_id": str(payload.merchant_id),
        "endpoint": "/internal/campaigns/run",
        "request_id": request_id,
    }

    with propagate_attributes(
        trace_name="run-campaign", tags=["campaign"], metadata=trace_metadata, environment=settings.app_env
    ):
        # get_current_trace_id() must be called inside propagate_attributes so
        # the OTel span is active and the ID is non-None — same as router_checkout.
        trace_id = langfuse.get_current_trace_id()
        langfuse.update_current_span(
            input={"merchant_id": str(payload.merchant_id), "window_hours": payload.window_hours}
        )

        agent_run = AgentRun(
            id=uuid.uuid4(),
            merchant_id=payload.merchant_id,
            type="campaign",
            status="running",
            langfuse_trace_id=trace_id,
            started_at=datetime.now(timezone.utc),
        )
        db.add(agent_run)
        await db.commit()

        initial_state: CampaignState = {
            "merchant_id": str(payload.merchant_id),
            "agent_run_id": str(agent_run.id),
            "window_hours": payload.window_hours,
        }

        graph = build_campaign_graph(db)
        # run_name replaces the generic "LangGraph" label the callback handler
        # would otherwise give this span (see Langfuse's LangGraph cookbook).
        graph_config = {"callbacks": [get_langfuse_handler()], "run_name": "campaign-graph"}

        try:
            result: CampaignState = await graph.ainvoke(initial_state, config=graph_config)
        except Exception as e:
            agent_run.status = "failed"
            agent_run.ended_at = datetime.now(timezone.utc)
            await db.commit()
            langfuse.update_current_span(output={"status": "failed", "error": str(e)})
            await asyncio.to_thread(langfuse.flush)
            raise

        agent_run.status = "success"
        agent_run.ended_at = datetime.now(timezone.utc)
        await db.commit()

        actions = [CampaignActionResult(**a) for a in result.get("actions") or []]
        langfuse.update_current_span(output={"status": "success", "action_count": len(actions)})
        await asyncio.to_thread(langfuse.flush)

        return CampaignRunResponse(actions=actions)
