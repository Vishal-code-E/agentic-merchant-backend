import uuid

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ProductCreate(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    merchant_id: uuid.UUID
    name: str
    description: str | None = None
    price: float
    currency: str = "INR"
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    stock: int = 0


class ProductUpdate(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    name: str | None = None
    description: str | None = None
    price: float | None = None
    currency: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    stock: int | None = None


class ProductResponse(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)

    id: uuid.UUID
    merchant_id: uuid.UUID
    name: str
    description: str | None
    price: float
    currency: str
    category: str | None
    tags: list[str]
    stock: int


class AgentCatalogItem(BaseModel):
    """Flat, agent/LLM-consumable catalog item — no nested objects, no merchant/internal fields."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    price: float
    currency: str
    category: str | None
    tags: list[str]
    stock: int
