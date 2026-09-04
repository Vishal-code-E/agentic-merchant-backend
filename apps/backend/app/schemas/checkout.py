import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.schemas.product import ProductResponse

CheckoutStatus = Literal["pending", "success", "failed"]


class CheckoutCartItem(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    product_id: uuid.UUID
    quantity: int


class CheckoutRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    merchant_id: uuid.UUID
    cart_items: list[CheckoutCartItem]
    customer_context: dict[str, Any] | None = None


class CheckoutResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    status: CheckoutStatus
    razorpay_order_id: str | None
    amount: float
    currency: str
    upsell_suggestions: list[ProductResponse] = Field(default_factory=list)
    explanation: str


class ChatCheckoutRequest(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    message: str
    merchant_id: uuid.UUID
    customer_context: dict[str, Any] | None = None


class ChatCheckoutResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    interpretation: str
    checkout_result: CheckoutResponse | None = None
    matched: bool
