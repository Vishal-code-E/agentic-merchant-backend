import uuid

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Merchant(Base, TimestampMixin):
    """
    A Razorpay merchant onboarded onto the agentic backend.

    NOTE: razorpay_key_secret must be stored encrypted at rest in a real
    deployment (e.g. via a secrets manager or column-level encryption).
    This skeleton stores the field but does not yet implement encryption —
    tracked as a v1.0 TODO, not to be skipped before any real key is stored.
    """
    __tablename__ = "merchants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    razorpay_key_id: Mapped[str] = mapped_column(String(255), nullable=True)
    razorpay_key_secret: Mapped[str] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending|active|disabled
