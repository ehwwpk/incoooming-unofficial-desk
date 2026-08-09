"""Add versioned local workspace preferences."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260809_0004"
down_revision: str | None = "20260809_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspace_preferences",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_key", sa.String(length=128), nullable=False),
        sa.Column("workspace_key", sa.String(length=32), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workspace_preferences")),
        sa.UniqueConstraint(
            "owner_key", "workspace_key", name=op.f("uq_workspace_preferences_owner_key")
        ),
    )
    op.create_index(
        op.f("ix_workspace_preferences_owner_key"), "workspace_preferences", ["owner_key"]
    )
    op.create_index(
        op.f("ix_workspace_preferences_workspace_key"),
        "workspace_preferences",
        ["workspace_key"],
    )


def downgrade() -> None:
    op.drop_table("workspace_preferences")
