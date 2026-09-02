import uuid

from pydantic import BaseModel, ConfigDict


class OnboardMerchantRequest(BaseModel):
    name: str
    razorpay_key_id: str
    razorpay_key_secret: str


class MerchantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    razorpay_key_id: str | None
    status: str


class OnboardMerchantResponse(BaseModel):
    merchant: MerchantResponse
    keys_valid: bool
