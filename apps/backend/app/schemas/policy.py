import uuid

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class PolicyResponse(BaseModel):
    """Merchant guardrails as returned to the dashboard / shared-types clients."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)

    id: uuid.UUID
    merchant_id: uuid.UUID
    max_amount: float | None
    allowed_categories: list[str]
    per_user_limit: float | None


class PolicyUpdate(BaseModel):
    """
    Partial update for an existing merchant's policy. Every field is optional;
    only fields actually present in the request body are applied
    (see router_policy.update_policy, which uses exclude_unset=True).

    Note the asymmetry with OnboardMerchantRequest: there, max_amount is
    required. Here it is optional-but-not-nullable, so a policy cannot be
    stripped of its ceiling once set — PolicyEngine.evaluate() fails closed on
    a missing max_amount and every checkout for that merchant would 403.
    """

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    max_amount: float | None = Field(default=None, gt=0)
    allowed_categories: list[str] | None = None
    per_user_limit: float | None = Field(default=None, gt=0)
