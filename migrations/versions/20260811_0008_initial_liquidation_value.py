"""Preserve Schwab's start-of-day account value for truthful day change."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260811_0008"
down_revision: str | None = "20260810_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "account_balance_snapshots",
        sa.Column("initial_liquidation_value", sa.Numeric(28, 10), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("account_balance_snapshots", "initial_liquidation_value")
