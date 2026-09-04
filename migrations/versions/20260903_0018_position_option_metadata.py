"""Store option multiplier and standardness on position anchors."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260903_0018"
down_revision: str | None = "20260814_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("position_snapshots") as batch:
        batch.add_column(sa.Column("contract_multiplier", sa.Numeric(28, 10)))
        batch.add_column(sa.Column("is_non_standard", sa.Boolean(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("position_snapshots") as batch:
        batch.drop_column("is_non_standard")
        batch.drop_column("contract_multiplier")
