"""Writes structured AuditLog entries linking intent -> policy check -> external call -> outcome."""
from typing import Any


class AuditService:
    async def log_event(
        self,
        agent_run_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        """TODO(v1.3): persist an AuditLog row via the DB session."""
        raise NotImplementedError
