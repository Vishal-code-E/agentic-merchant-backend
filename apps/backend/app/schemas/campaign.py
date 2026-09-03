import uuid

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CampaignRunRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    merchant_id: uuid.UUID
    window_hours: int = Field(default=24, gt=0)


class CampaignRunResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    actions: list[dict] = Field(default_factory=list)
