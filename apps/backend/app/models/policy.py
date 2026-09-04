import uuid

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.merchant import Merchant


class Policy(Base, TimestampMixin):
    """
    Per-merchant guardrails. Every money-moving graph node must consult
    this before calling out to Razorpay (see Graph Engineering doc, §2.3
    "Policy before payment").
    """
    __tablename__ = "policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)
    #: Set this instead of merchant_id when creating a Policy alongside a new
    #: Merchant — it lets both rows INSERT in one flush (router_onboarding).
    merchant: Mapped[Merchant] = relationship()
    max_amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=True)
    allowed_categories: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    per_user_limit: Mapped[float] = mapped_column(Numeric(12, 2), nullable=True)
    max_discount_pct: Mapped[float] = mapped_column(Numeric(5, 2), default=30.0, nullable=False)
    rules_json: Mapped[dict] = mapped_column(JSONB, default=dict)
