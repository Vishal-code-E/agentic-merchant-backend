import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.agent_run import AgentRun
from app.models.audit_log import AuditLog
from app.schemas.observability import AgentRunResponse, AuditLogResponse

router = APIRouter(tags=["observability"])


@router.get("/observability/agent-runs", response_model=list[AgentRunResponse])
async def list_agent_runs(
    merchant_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    """List AgentRun records, most recent first, optionally scoped to one merchant."""
    query = select(AgentRun).order_by(AgentRun.created_at.desc())
    if merchant_id is not None:
        query = query.where(AgentRun.merchant_id == merchant_id)

    result = await db.execute(query)
    return result.scalars().all()


@router.get(
    "/observability/agent-runs/{agent_run_id}/audit-logs",
    response_model=list[AuditLogResponse],
)
async def get_audit_logs_for_run(agent_run_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Detail view: the audit trail for a single agent run, oldest first."""
    agent_run = await db.get(AgentRun, agent_run_id)
    if agent_run is None:
        raise HTTPException(status_code=404, detail="Agent run not found")

    result = await db.execute(
        select(AuditLog).where(AuditLog.agent_run_id == agent_run_id).order_by(AuditLog.created_at.asc())
    )
    return result.scalars().all()
