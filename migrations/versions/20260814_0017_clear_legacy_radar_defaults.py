"""Remove legacy Radar limits that were inserted as automatic defaults."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260814_0017"
down_revision: str | None = "20260814_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # These exact values came from the old form defaults. The prior schema could
    # not record whether the user explicitly chose them, so opt for the requested
    # no-filter behavior and let a future edit save an explicit limit again.
    op.execute(
        sa.text(
            "UPDATE radar_policies "
            "SET maximum_spread_percent = NULL "
            "WHERE maximum_spread_percent = 25"
        )
    )
    op.execute(
        sa.text(
            "UPDATE radar_policies "
            "SET maximum_five_day_move_percent = NULL "
            "WHERE maximum_five_day_move_percent = 20"
        )
    )


def downgrade() -> None:
    # A no-limit value may have been an explicit post-upgrade choice. Restoring
    # the retired automatic limits would overwrite that intent, so leave it null.
    pass
