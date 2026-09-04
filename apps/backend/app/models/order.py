import uuid

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Order(Base, TimestampMixin):
    """Internal order record, linked 1:1 with a Razorpay test-mode Order."""
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False)
    razorpay_order_id: Mapped[str] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending|success|failed
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    cart_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)
    #: Caller-supplied Idempotency-Key from POST /agent/checkout. Nullable for
    #: rows predating this column; unique per (merchant_id, idempotency_key)
    #: at the DB level (see alembic/versions/0004_orders_idempotency_key.py) —
    #: create_order_node checks this before ever calling Razorpay.
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
