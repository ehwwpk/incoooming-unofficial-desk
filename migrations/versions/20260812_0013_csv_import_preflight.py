"""Add broker CSV preflight, row dispositions, and format metadata."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260812_0013"
down_revision: str | None = "20260812_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "source_datasets",
        sa.Column("ignored_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "source_datasets",
        sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "source_datasets",
        sa.Column("capabilities", sa.JSON(), nullable=False, server_default="[]"),
    )
    for name, type_, default in (
        ("source_row_count", sa.Integer(), "0"),
        ("ignored_count", sa.Integer(), "0"),
        ("review_count", sa.Integer(), "0"),
        ("detected_broker", sa.String(24), "generic"),
        ("profile", sa.String(64), "legacy"),
        ("confidence", sa.String(16), "unknown"),
        ("header_row", sa.Integer(), "1"),
        ("encoding", sa.String(24), "utf-8"),
        ("delimiter", sa.String(4), ","),
    ):
        op.add_column(
            "source_import_files",
            sa.Column(name, type_, nullable=False, server_default=default),
        )
    op.add_column(
        "source_import_files",
        sa.Column("capabilities", sa.JSON(), nullable=False, server_default="[]"),
    )
    for name, type_, default in (
        ("disposition", sa.String(24), "imported"),
        ("source_row_number", sa.Integer(), "0"),
        ("fingerprint", sa.String(64), ""),
    ):
        op.add_column(
            "source_import_records",
            sa.Column(name, type_, nullable=False, server_default=default),
        )


def downgrade() -> None:
    for name in ("fingerprint", "source_row_number", "disposition"):
        op.drop_column("source_import_records", name)
    for name in (
        "capabilities",
        "delimiter",
        "encoding",
        "header_row",
        "confidence",
        "profile",
        "detected_broker",
        "review_count",
        "ignored_count",
        "source_row_count",
    ):
        op.drop_column("source_import_files", name)
    for name in ("capabilities", "review_count", "ignored_count"):
        op.drop_column("source_datasets", name)
