"""Add composite indexes for symbol-scoped latest-market reads."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260813_0014"
down_revision: str | None = "20260812_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_underlying_market_instrument_raw_event",
        "underlying_market_snapshots",
        ["instrument_id", "raw_event_id"],
    )
    op.create_index(
        "ix_option_market_instrument_raw_event",
        "option_market_snapshots",
        ["instrument_id", "raw_event_id"],
    )
    op.create_index(
        "ix_daily_bars_instrument_date_raw_event",
        "underlying_daily_bars",
        ["instrument_id", "trade_date", "raw_event_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_daily_bars_instrument_date_raw_event",
        table_name="underlying_daily_bars",
    )
    op.drop_index(
        "ix_option_market_instrument_raw_event",
        table_name="option_market_snapshots",
    )
    op.drop_index(
        "ix_underlying_market_instrument_raw_event",
        table_name="underlying_market_snapshots",
    )
