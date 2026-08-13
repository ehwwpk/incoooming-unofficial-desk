"""Add isolated broker-file datasets and auditable imported rows.

Revision ID: 20260811_0011
Revises: 20260811_0010
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260811_0011"
down_revision: str | None = "20260811_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_datasets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("broker", sa.String(length=24), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("file_count", sa.Integer(), nullable=False),
        sa.Column("position_count", sa.Integer(), nullable=False),
        sa.Column("activity_count", sa.Integer(), nullable=False),
        sa.Column("rejected_count", sa.Integer(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "source_import_files",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("file_kind", sa.String(length=24), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("headers", sa.JSON(), nullable=False),
        sa.Column("record_count", sa.Integer(), nullable=False),
        sa.Column("rejected_count", sa.Integer(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["source_datasets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "sha256", name="uq_source_import_file_hash"),
    )
    op.create_table(
        "source_import_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("dataset_id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("record_kind", sa.String(length=24), nullable=False),
        sa.Column("external_key", sa.String(length=160), nullable=False),
        sa.Column("normalized", sa.JSON(), nullable=False),
        sa.Column("raw", sa.JSON(), nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["dataset_id"], ["source_datasets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["file_id"], ["source_import_files.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "dataset_id",
            "external_key",
            name="uq_source_import_record_external_key",
        ),
    )
    op.create_index(
        "ix_source_import_records_dataset_kind",
        "source_import_records",
        ["dataset_id", "record_kind"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_source_import_records_dataset_kind",
        table_name="source_import_records",
    )
    op.drop_table("source_import_records")
    op.drop_table("source_import_files")
    op.drop_table("source_datasets")
