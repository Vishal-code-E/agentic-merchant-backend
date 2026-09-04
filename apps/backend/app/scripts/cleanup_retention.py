"""
Retention cleanup worker / CLI script.

Purges audit_logs and terminal agent_runs older than a configurable retention
window (default: settings.data_retention_days or 90 days).

Usage:
    python -m app.scripts.cleanup_retention [--days 90] [--dry-run]
"""
import argparse
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.db.session import async_session_factory
from app.models.agent_run import AgentRun
from app.models.audit_log import AuditLog

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("retention_cleanup")


async def purge_retention_records(
    db: AsyncSession,
    retention_days: int | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """
    Purge audit logs and completed agent runs older than retention_days.
    Returns counts of identified or deleted records.
    """
    settings = get_settings()
    days = retention_days if retention_days is not None else settings.data_retention_days
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    logger.info("Evaluating retention cleanup for records older than %s (%d days)...", cutoff.isoformat(), days)

    # 1. Count / select old audit logs
    audit_count_res = await db.execute(
        select(AuditLog.id).where(AuditLog.created_at < cutoff)
    )
    expired_audit_ids = audit_count_res.scalars().all()
    audit_count = len(expired_audit_ids)

    # 2. Count / select old completed agent runs
    run_count_res = await db.execute(
        select(AgentRun.id).where(
            AgentRun.created_at < cutoff,
            AgentRun.status.in_(["success", "failed"]),
        )
    )
    expired_run_ids = run_count_res.scalars().all()
    run_count = len(expired_run_ids)

    if dry_run:
        logger.info(
            "[DRY RUN] Would purge %d audit logs and %d terminal agent runs.",
            audit_count,
            run_count,
        )
        return {"purged_audit_logs": audit_count, "purged_agent_runs": run_count, "dry_run": True}

    # Execute deletion
    if expired_audit_ids:
        await db.execute(
            delete(AuditLog).where(AuditLog.id.in_(expired_audit_ids))
        )

    if expired_run_ids:
        # Note: if any remaining audit logs reference these runs, Postgres FK constraint
        # will protect them. Since we deleted old audit logs first, orphaned old runs can now be safely deleted.
        # We only delete runs whose audit logs are completely gone.
        referencing_logs = await db.execute(
            select(AuditLog.agent_run_id).where(AuditLog.agent_run_id.in_(expired_run_ids))
        )
        active_referenced_run_ids = set(referencing_logs.scalars().all())
        safe_to_delete_runs = [r_id for r_id in expired_run_ids if r_id not in active_referenced_run_ids]

        if safe_to_delete_runs:
            await db.execute(
                delete(AgentRun).where(AgentRun.id.in_(safe_to_delete_runs))
            )
            run_count = len(safe_to_delete_runs)
        else:
            run_count = 0

    await db.commit()
    logger.info("Successfully purged %d audit logs and %d agent runs.", audit_count, run_count)
    return {"purged_audit_logs": audit_count, "purged_agent_runs": run_count, "dry_run": False}


async def main():
    parser = argparse.ArgumentParser(description="Purge audit logs and agent runs older than retention window.")
    parser.add_argument("--days", type=int, default=None, help="Retention period in days (default from settings: 90)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate purge without deleting records")
    args = parser.parse_args()

    async with async_session_factory() as db:
        result = await purge_retention_records(db, retention_days=args.days, dry_run=args.dry_run)
        print(f"Cleanup Result: {result}")


if __name__ == "__main__":
    asyncio.run(main())
