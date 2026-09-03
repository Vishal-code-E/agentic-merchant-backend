import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.policy import PolicyResponse


class OnboardMerchantRequest(BaseModel):
    name: str
    razorpay_key_id: str
    razorpay_key_secret: str

    # v1.2: a merchant cannot exist without a policy, so the guardrails are
    # part of the onboarding contract rather than a follow-up call.
    max_amount: float = Field(gt=0, description="Per-checkout ceiling, in the catalog currency.")
    allowed_categories: list[str] = Field(
        default_factory=list,
        description="Empty list means no category restriction.",
    )
    per_user_limit: float | None = Field(default=None, gt=0)


class MerchantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    razorpay_key_id: str | None
    status: str


class OnboardMerchantResponse(BaseModel):
    merchant: MerchantResponse
    policy: PolicyResponse
    keys_valid: bool
