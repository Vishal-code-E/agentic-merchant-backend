import uuid
from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Merchant(Base, TimestampMixin):
    """
    A Razorpay merchant onboarded onto the agentic backend.

    razorpay_key_secret is stored Fernet-encrypted (see app/services/encryption.py).
    Decrypt only at the point of instantiating a RazorpayClient — never log or
    return the decrypted value.

    api_key_hash is a sha256 hex digest of this merchant's agent API key (see
    app/services/agent_auth.py) — one-way, unlike the Fernet-reversible
    Razorpay secret, since the key is only ever compared, never presented to
    a downstream service. The plaintext key itself is generated once at
    onboarding, returned in that response, and never stored or shown again.
    """
    __tablename__ = "merchants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    razorpay_key_id: Mapped[str] = mapped_column(String(255), nullable=True)
    razorpay_key_secret: Mapped[str] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending|active|disabled
    api_key_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: Set on every successful verify_agent_api_key() call (see agent_auth.py) — a coarse "is this key still alive" signal.
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deactivated_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
