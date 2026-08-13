"""Add isolated Premium Radar policies, lookups, and candidate audit rows."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260811_0010"
down_revision: str | None = "20260811_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "radar_policies",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("minimum_dte", sa.Integer(), nullable=False),
        sa.Column("maximum_dte", sa.Integer(), nullable=False),
        sa.Column("minimum_strike", sa.Numeric(28, 10), nullable=True),
        sa.Column("minimum_strike_distance_percent", sa.Numeric(28, 10), nullable=False),
        sa.Column("maximum_effective_entry", sa.Numeric(28, 10), nullable=True),
        sa.Column("maximum_spread_percent", sa.Numeric(28, 10), nullable=False),
        sa.Column("minimum_open_interest", sa.Integer(), nullable=False),
        sa.Column("minimum_volume", sa.Integer(), nullable=False),
        sa.Column("maximum_quote_age_seconds", sa.Integer(), nullable=False),
        sa.Column("allowed_contracts", sa.Integer(), nullable=False),
        sa.Column("reserved_cash", sa.Numeric(28, 10), nullable=False),
        sa.Column("maximum_five_day_move_percent", sa.Numeric(28, 10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", "mode"),
    )
    op.create_index("ix_radar_policies_symbol", "radar_policies", ["symbol"])
    op.create_index("ix_radar_policies_mode", "radar_policies", ["mode"])

    op.create_table(
        "radar_saved_symbols",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "symbol"),
    )
    op.create_index("ix_radar_saved_symbols_source", "radar_saved_symbols", ["source"])
    op.create_index("ix_radar_saved_symbols_symbol", "radar_saved_symbols", ["symbol"])

    op.create_table(
        "radar_lookup_runs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("symbol", sa.String(16), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("policy_version", sa.Integer(), nullable=True),
        sa.Column("projection", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.String(512), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "source",
        "symbol",
        "mode",
        "state",
        "requested_at",
        "completed_at",
        "observed_at",
    ):
        op.create_index(f"ix_radar_lookup_runs_{column}", "radar_lookup_runs", [column])

    op.create_table(
        "radar_candidate_snapshots",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("lookup_id", sa.String(36), nullable=False),
        sa.Column("option_symbol", sa.String(64), nullable=False),
        sa.Column("frontier_label", sa.String(32), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("gates", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["lookup_id"], ["radar_lookup_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lookup_id", "option_symbol"),
    )
    op.create_index(
        "ix_radar_candidate_snapshots_lookup_id",
        "radar_candidate_snapshots",
        ["lookup_id"],
    )
    op.create_index(
        "ix_radar_candidate_snapshots_option_symbol",
        "radar_candidate_snapshots",
        ["option_symbol"],
    )


def downgrade() -> None:
    op.drop_table("radar_candidate_snapshots")
    op.drop_table("radar_lookup_runs")
    op.drop_table("radar_saved_symbols")
    op.drop_table("radar_policies")
