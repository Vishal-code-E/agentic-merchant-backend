"""add merchants.last_used_at, agent_runs.agent_name/agent_version

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-04

All three columns are nullable and not backfilled: last_used_at has no
historical data to backfill (auth checks predating this migration weren't
recorded), and agent_name/agent_version are informational identity fields
supplied by the caller per-request (see router_checkout.py) — existing
agent_runs rows simply have no opinion on either.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("merchants", sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agent_runs", sa.Column("agent_name", sa.String(length=255), nullable=True))
    op.add_column("agent_runs", sa.Column("agent_version", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_runs", "agent_version")
    op.drop_column("agent_runs", "agent_name")
    op.drop_column("merchants", "last_used_at")
