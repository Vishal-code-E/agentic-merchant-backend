import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    max_discount_pct: float = Field(
        default=30.0,
        ge=0.0,
        le=50.0,
        description="Max discount % (0-50%) permitted for autonomous campaign suggestions.",
    )

    @model_validator(mode="after")
    def validate_limits(self) -> "OnboardMerchantRequest":
        if self.per_user_limit is not None and self.per_user_limit > self.max_amount:
            raise ValueError("per_user_limit cannot exceed max_amount.")
        return self


class MerchantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    razorpay_key_id: str | None
    status: str
    deleted_at: datetime | None = None


class OnboardMerchantResponse(BaseModel):
    merchant: MerchantResponse
    policy: PolicyResponse
    keys_valid: bool
    # Plaintext agent API key — returned exactly once, here, same pattern as
    # Razorpay's own key_secret being shown once on the Razorpay dashboard.
    # Never stored in plaintext (see Merchant.api_key_hash) and never
    # returned by any other endpoint, including GET /merchant/{merchant_id}.
    api_key: str


class RegenerateApiKeyResponse(BaseModel):
    merchant_id: uuid.UUID
    # Plaintext — same one-time-only contract as OnboardMerchantResponse.api_key.
    # Invalidates the merchant's previous key immediately.
    api_key: str


class DeactivateMerchantRequest(BaseModel):
    reason: str | None = None
    anonymize_audit_logs: bool = True


class DeactivateMerchantResponse(BaseModel):
    merchant_id: uuid.UUID
    status: str
    deactivated_at: datetime
    retained_records: dict[str, int]
    notice: str
