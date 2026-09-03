"""enforce 1:1 merchant<->policy invariant with a unique constraint

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-03

No backfill here: one pre-v1.2 merchant is still missing a Policy row and is
being repaired manually (out of band). A missing row does not violate a
uniqueness constraint, so this migration is safe to apply while that gap
exists — it only prevents a second Policy row ever being inserted for the
same merchant_id going forward.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_policies_merchant_id",
        "policies",
        ["merchant_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_policies_merchant_id", "policies", type_="unique")
