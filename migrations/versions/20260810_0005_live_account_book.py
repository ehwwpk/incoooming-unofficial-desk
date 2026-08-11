"""Preserve live account balances and option contract identity."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260810_0005"
down_revision: str | None = "20260809_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "position_snapshots",
        sa.Column("description", sa.String(512), nullable=False, server_default=""),
    )
    op.add_column("position_snapshots", sa.Column("underlying_symbol", sa.String(64)))
    op.add_column("position_snapshots", sa.Column("option_type", sa.String(16)))
    op.add_column("position_snapshots", sa.Column("expiration_date", sa.DateTime()))
    op.add_column("position_snapshots", sa.Column("strike", sa.Numeric(28, 10)))
    op.add_column("position_snapshots", sa.Column("long_open_profit_loss", sa.Numeric(28, 10)))
    op.add_column("position_snapshots", sa.Column("short_open_profit_loss", sa.Numeric(28, 10)))
    op.create_index(
        op.f("ix_position_snapshots_underlying_symbol"), "position_snapshots", ["underlying_symbol"]
    )
    op.create_index(
        op.f("ix_position_snapshots_option_type"), "position_snapshots", ["option_type"]
    )

    op.create_table(
        "account_balance_snapshots",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.Column("sync_run_id", sa.String(36), nullable=False),
        sa.Column("raw_event_id", sa.String(36), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("liquidation_value", sa.Numeric(28, 10)),
        sa.Column("equity", sa.Numeric(28, 10)),
        sa.Column("cash_balance", sa.Numeric(28, 10)),
        sa.Column("money_market_fund", sa.Numeric(28, 10)),
        sa.Column("margin_balance", sa.Numeric(28, 10)),
        sa.Column("buying_power", sa.Numeric(28, 10)),
        sa.Column("available_funds", sa.Numeric(28, 10)),
        sa.Column("maintenance_requirement", sa.Numeric(28, 10)),
        sa.Column("long_market_value", sa.Numeric(28, 10)),
        sa.Column("short_market_value", sa.Numeric(28, 10)),
        sa.Column("long_option_market_value", sa.Numeric(28, 10)),
        sa.Column("short_option_market_value", sa.Numeric(28, 10)),
        sa.Column("is_portfolio_margin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_intraday_margin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sync_run_id"], ["sync_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["raw_event_id"], ["raw_broker_events.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sync_run_id", "account_id"),
    )
    op.create_index(
        op.f("ix_account_balance_snapshots_account_id"), "account_balance_snapshots", ["account_id"]
    )
    op.create_index(
        op.f("ix_account_balance_snapshots_sync_run_id"),
        "account_balance_snapshots",
        ["sync_run_id"],
    )


def downgrade() -> None:
    op.drop_table("account_balance_snapshots")
    op.drop_index(op.f("ix_position_snapshots_option_type"), table_name="position_snapshots")
    op.drop_index(op.f("ix_position_snapshots_underlying_symbol"), table_name="position_snapshots")
    for column in (
        "short_open_profit_loss",
        "long_open_profit_loss",
        "strike",
        "expiration_date",
        "option_type",
        "underlying_symbol",
        "description",
    ):
        op.drop_column("position_snapshots", column)
