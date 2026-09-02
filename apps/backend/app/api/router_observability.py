from fastapi import APIRouter

router = APIRouter(tags=["observability"])


@router.get("/observability/agent-runs")
async def list_agent_runs():
    """List AgentRun records with status + Langfuse trace links. TODO(v1.3)."""
    raise NotImplementedError


@router.get("/observability/agent-runs/{agent_run_id}/audit-logs")
async def get_audit_logs_for_run(agent_run_id: str):
    """Detail view: audit trail for a single agent run. TODO(v1.3)."""
    raise NotImplementedError
