import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CampaignRunRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    merchant_id: uuid.UUID
    window_hours: int = Field(default=24, gt=0)


class CampaignActionResult(BaseModel):
    """One action that survived ApplyPolicy — order-level, expanded from a
    segment-level growth_agent.CampaignAction (see campaign_graph.py)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    order_id: str
    segment: str
    action: str
    amount: float
    currency: str
    reasoning: str
    confidence: float
    suggested_discount_pct: float | None
    #: Which recommendation source produced this — see docs/ARCHITECTURE.md's Growth Agent section.
    path: Literal["llm_reasoning", "rule_based_fallback"]


class CampaignRunResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    actions: list[CampaignActionResult] = Field(default_factory=list)
