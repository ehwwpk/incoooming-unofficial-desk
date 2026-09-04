"""Preserve unknown legacy option standardness instead of assuming standard."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260903_0020"
down_revision: str | None = "20260903_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("position_snapshots") as batch:
        batch.alter_column(
            "is_non_standard",
            existing_type=sa.Boolean(),
            nullable=True,
            server_default=None,
        )
    op.execute(
        """
        UPDATE position_snapshots
        SET is_non_standard = NULL
        WHERE asset_type = 'OPTION'
          AND contract_multiplier IS NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE position_snapshots
        SET is_non_standard = 0
        WHERE is_non_standard IS NULL
        """
    )
    with op.batch_alter_table("position_snapshots") as batch:
        batch.alter_column(
            "is_non_standard",
            existing_type=sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        )
