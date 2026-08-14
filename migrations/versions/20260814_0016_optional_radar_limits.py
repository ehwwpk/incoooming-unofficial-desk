"""Make optional Radar spread and momentum limits truly opt-in."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260814_0016"
down_revision: str | None = "20260813_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("radar_policies") as batch_op:
        batch_op.alter_column(
            "maximum_spread_percent",
            existing_type=sa.Numeric(28, 10),
            nullable=True,
        )

    # The old UI used 100% as a practical "off" switch. Preserve ordinary saved
    # limits but translate that workaround into the new explicit no-limit state.
    op.execute(
        sa.text(
            "UPDATE radar_policies "
            "SET maximum_spread_percent = NULL "
            "WHERE maximum_spread_percent >= 100"
        )
    )
    op.execute(
        sa.text(
            "UPDATE radar_policies "
            "SET maximum_five_day_move_percent = NULL "
            "WHERE maximum_five_day_move_percent >= 100"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE radar_policies "
            "SET maximum_spread_percent = 100 "
            "WHERE maximum_spread_percent IS NULL"
        )
    )
    with op.batch_alter_table("radar_policies") as batch_op:
        batch_op.alter_column(
            "maximum_spread_percent",
            existing_type=sa.Numeric(28, 10),
            nullable=False,
        )
