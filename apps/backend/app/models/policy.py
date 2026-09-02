import uuid

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Policy(Base, TimestampMixin):
    """
    Per-merchant guardrails. Every money-moving graph node must consult
    this before calling out to Razorpay (see Graph Engineering doc, §2.3
    "Policy before payment").
    """
    __tablename__ = "policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)
    max_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=True)
    allowed_categories: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    per_user_limit: Mapped[float] = mapped_column(Numeric(12, 2), nullable=True)
    rules_json: Mapped[dict] = mapped_column(JSONB, default=dict)
