import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class AgentRunResponse(BaseModel):
    """One execution of checkout_graph or campaign_graph."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)

    id: uuid.UUID
    merchant_id: uuid.UUID
    type: str
    status: str
    langfuse_trace_id: str | None
    started_at: datetime | None
    ended_at: datetime | None


class AuditLogResponse(BaseModel):
    """
    Structured audit trail entry for one AgentRun.

    The DB column is payload_json, but the wire/shared-types contract calls it
    `payload` (see libs/shared-types/src/index.ts AuditLogEntry) — validation_alias
    pulls the ORM attribute by its real name while the (single-word) field name
    itself already matches the camelCase output the alias_generator would produce.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)

    id: uuid.UUID
    agent_run_id: uuid.UUID
    event_type: str
    payload: dict = Field(validation_alias="payload_json")
    created_at: datetime
