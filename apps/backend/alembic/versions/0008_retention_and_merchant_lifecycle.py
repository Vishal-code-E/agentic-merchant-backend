"""Add retention indexes, merchant deactivation columns, and policy discount limits

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-04

Safeguards:
1. merchants.deleted_at & deactivated_reason for soft-delete / GDPR deactivation.
2. policies.max_discount_pct with [0, 50] check constraint to prevent infinite/runaway discounts.
3. indexes on audit_logs(created_at) and agent_runs(created_at) for efficient retention purging.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Merchant lifecycle columns
    op.add_column("merchants", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("merchants", sa.Column("deactivated_reason", sa.String(255), nullable=True))

    # 2. Policy discount guardrail
    op.add_column(
        "policies",
        sa.Column("max_discount_pct", sa.Numeric(5, 2), server_default="30.00", nullable=False),
    )
    op.create_check_constraint(
        "ck_policies_max_discount_pct_range",
        "policies",
        "max_discount_pct >= 0 AND max_discount_pct <= 50",
    )

    # 3. Retention lookup indices
    op.create_index("idx_audit_logs_created_at", "audit_logs", ["created_at"])
    op.create_index("idx_agent_runs_created_at", "agent_runs", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_agent_runs_created_at", table_name="agent_runs")
    op.drop_index("idx_audit_logs_created_at", table_name="audit_logs")
    op.drop_constraint("ck_policies_max_discount_pct_range", "policies", type_="check")
    op.drop_column("policies", "max_discount_pct")
    op.drop_column("merchants", "deactivated_reason")
    op.drop_column("merchants", "deleted_at")
