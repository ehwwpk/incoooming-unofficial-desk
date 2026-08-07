"""Create the Phase 1 account and position observation ledger."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260807_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sync_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("account_count", sa.Integer(), nullable=False),
        sa.Column("position_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sync_runs")),
    )
    op.create_index(op.f("ix_sync_runs_source"), "sync_runs", ["source"])
    op.create_index(op.f("ix_sync_runs_status"), "sync_runs", ["status"])

    op.create_table(
        "accounts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("external_account_key", sa.String(length=256), nullable=False),
        sa.Column("account_mask", sa.String(length=32), nullable=False),
        sa.Column("account_type", sa.String(length=64), nullable=False),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_accounts")),
        sa.UniqueConstraint("source", "external_account_key", name=op.f("uq_accounts_source")),
    )

    op.create_table(
        "raw_broker_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("sync_run_id", sa.String(length=36), nullable=False),
        sa.Column("item_key", sa.String(length=256), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("account_external_key", sa.String(length=256), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("parser_version", sa.String(length=64), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["sync_run_id"],
            ["sync_runs.id"],
            name=op.f("fk_raw_broker_events_sync_run_id_sync_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_raw_broker_events")),
        sa.UniqueConstraint(
            "sync_run_id", "item_key", name=op.f("uq_raw_broker_events_sync_run_id")
        ),
    )
    op.create_index(
        op.f("ix_raw_broker_events_account_external_key"),
        "raw_broker_events",
        ["account_external_key"],
    )
    op.create_index(op.f("ix_raw_broker_events_event_type"), "raw_broker_events", ["event_type"])
    op.create_index(op.f("ix_raw_broker_events_sync_run_id"), "raw_broker_events", ["sync_run_id"])

    op.create_table(
        "position_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("sync_run_id", sa.String(length=36), nullable=False),
        sa.Column("raw_event_id", sa.String(length=36), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("instrument_key", sa.String(length=256), nullable=False),
        sa.Column("symbol", sa.String(length=128), nullable=False),
        sa.Column("asset_type", sa.String(length=32), nullable=False),
        sa.Column("long_quantity", sa.Numeric(28, 10), nullable=False),
        sa.Column("short_quantity", sa.Numeric(28, 10), nullable=False),
        sa.Column("average_price", sa.Numeric(28, 10), nullable=True),
        sa.Column("market_value", sa.Numeric(28, 10), nullable=True),
        sa.Column("day_profit_loss", sa.Numeric(28, 10), nullable=True),
        sa.Column("day_profit_loss_percent", sa.Numeric(28, 10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_position_snapshots_account_id_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["raw_event_id"],
            ["raw_broker_events.id"],
            name=op.f("fk_position_snapshots_raw_event_id_raw_broker_events"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["sync_run_id"],
            ["sync_runs.id"],
            name=op.f("fk_position_snapshots_sync_run_id_sync_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_position_snapshots")),
        sa.UniqueConstraint(
            "sync_run_id",
            "account_id",
            "instrument_key",
            name=op.f("uq_position_snapshots_sync_run_id"),
        ),
    )
    op.create_index(op.f("ix_position_snapshots_account_id"), "position_snapshots", ["account_id"])
    op.create_index(op.f("ix_position_snapshots_asset_type"), "position_snapshots", ["asset_type"])
    op.create_index(op.f("ix_position_snapshots_symbol"), "position_snapshots", ["symbol"])
    op.create_index(
        op.f("ix_position_snapshots_sync_run_id"), "position_snapshots", ["sync_run_id"]
    )

    op.create_table(
        "reconciliation_issues",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("sync_run_id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("account_external_key", sa.String(length=256), nullable=False),
        sa.Column("instrument_key", sa.String(length=256), nullable=True),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["sync_run_id"],
            ["sync_runs.id"],
            name=op.f("fk_reconciliation_issues_sync_run_id_sync_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reconciliation_issues")),
    )
    op.create_index(op.f("ix_reconciliation_issues_code"), "reconciliation_issues", ["code"])
    op.create_index(
        op.f("ix_reconciliation_issues_severity"), "reconciliation_issues", ["severity"]
    )
    op.create_index(
        op.f("ix_reconciliation_issues_sync_run_id"),
        "reconciliation_issues",
        ["sync_run_id"],
    )


def downgrade() -> None:
    op.drop_table("reconciliation_issues")
    op.drop_table("position_snapshots")
    op.drop_table("raw_broker_events")
    op.drop_table("accounts")
    op.drop_table("sync_runs")
