"""add idempotency_key to orders, unique per (merchant_id, idempotency_key)

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-05

Nullable: existing pre-idempotency Order rows have no key, and Postgres
treats each NULL as distinct under a unique constraint, so any number of
pre-existing NULL rows coexist safely — this constraint only prevents two
rows for the same merchant ever sharing the same non-null idempotency_key
going forward. Enforcement that a *new* checkout must supply one lives in
the API layer (POST /agent/checkout 400s on a missing Idempotency-Key
header), not here.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("idempotency_key", sa.String(length=255), nullable=True))
    op.create_unique_constraint(
        "uq_orders_merchant_id_idempotency_key",
        "orders",
        ["merchant_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_orders_merchant_id_idempotency_key", "orders", type_="unique")
    op.drop_column("orders", "idempotency_key")
