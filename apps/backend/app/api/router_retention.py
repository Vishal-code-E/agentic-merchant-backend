"""
Retention cleanup admin endpoint for cron workers or dashboard triggers.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.scripts.cleanup_retention import purge_retention_records

router = APIRouter(tags=["retention"])


class RetentionCleanupRequest(BaseModel):
    days: int | None = Field(default=None, gt=0, description="Override retention days threshold (default: 90)")
    dry_run: bool = Field(default=False, description="Preview count of records without deleting")


class RetentionCleanupResponse(BaseModel):
    purged_audit_logs: int
    purged_agent_runs: int
    dry_run: bool


@router.post("/internal/retention/cleanup", response_model=RetentionCleanupResponse)
async def trigger_retention_cleanup(
    payload: RetentionCleanupRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    days = payload.days if payload else None
    dry_run = payload.dry_run if payload else False
    result = await purge_retention_records(db, retention_days=days, dry_run=dry_run)
    return RetentionCleanupResponse(**result)
