"""widen merchants.razorpay_key_secret for Fernet ciphertext

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-03

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "merchants",
        "razorpay_key_secret",
        existing_type=sa.String(length=255),
        type_=sa.String(length=512),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "merchants",
        "razorpay_key_secret",
        existing_type=sa.String(length=512),
        type_=sa.String(length=255),
        existing_nullable=True,
    )
