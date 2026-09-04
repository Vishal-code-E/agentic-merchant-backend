"""CHECK constraints enforcing money/stock invariants at the DB layer

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-04

Defense in depth: these hold even if a caller reaches the DB through
anything other than the Pydantic-validated API layer (a script, a future
admin tool, a bug). Nullable columns (policies.max_amount,
policies.per_user_limit) are only constrained when set — NULL means "no
limit configured", which is a valid, different state from "limit is zero".

If this fails to apply, it means existing data already violates one of
these invariants (e.g. a seeded product with a negative price) — fix the
data first; do not weaken the constraint to make the migration pass.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_policies_max_amount_positive", "policies", "max_amount IS NULL OR max_amount > 0"
    )
    op.create_check_constraint(
        "ck_policies_per_user_limit_positive", "policies", "per_user_limit IS NULL OR per_user_limit > 0"
    )
    op.create_check_constraint("ck_products_price_nonnegative", "products", "price >= 0")
    op.create_check_constraint("ck_products_stock_nonnegative", "products", "stock >= 0")
    op.create_check_constraint("ck_orders_amount_positive", "orders", "amount > 0")


def downgrade() -> None:
    op.drop_constraint("ck_orders_amount_positive", "orders", type_="check")
    op.drop_constraint("ck_products_stock_nonnegative", "products", type_="check")
    op.drop_constraint("ck_products_price_nonnegative", "products", type_="check")
    op.drop_constraint("ck_policies_per_user_limit_positive", "policies", type_="check")
    op.drop_constraint("ck_policies_max_amount_positive", "policies", type_="check")
