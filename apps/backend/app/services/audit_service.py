"""Writes structured AuditLog entries linking intent -> policy check -> external call -> outcome."""
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


class AuditService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_event(
        self,
        agent_run_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        """
        Persist an AuditLog row. Flushed, not committed — this rides along in
        whatever transaction the caller is already in, so it becomes durable
        exactly when the caller's own commit (or get_db()'s) does.
        """
        audit_log = AuditLog(
            agent_run_id=uuid.UUID(agent_run_id),
            event_type=event_type,
            payload_json=payload,
        )
        self.db.add(audit_log)
        await self.db.flush()
