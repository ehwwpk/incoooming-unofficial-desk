"""Add the Radar premium-rate floor and bounded DTE defaults."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260812_0012"
down_revision: str | None = "20260811_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "radar_policies",
        sa.Column(
            "minimum_annualized_rate_percent",
            sa.Numeric(28, 10),
            nullable=False,
            server_default="5",
        ),
    )
    op.execute("UPDATE radar_policies SET minimum_dte = 5 WHERE minimum_dte < 5")
    op.execute("UPDATE radar_policies SET minimum_dte = 5 WHERE minimum_dte = 14")
    op.execute("UPDATE radar_policies SET minimum_dte = 60 WHERE minimum_dte > 60")
    op.execute("UPDATE radar_policies SET maximum_dte = 5 WHERE maximum_dte < 5")
    op.execute("UPDATE radar_policies SET maximum_dte = 60 WHERE maximum_dte > 60")


def downgrade() -> None:
    op.drop_column("radar_policies", "minimum_annualized_rate_percent")
