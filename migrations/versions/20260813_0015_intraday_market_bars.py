"""Store timestamped intraday OHLCV bars for interval-aware charts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260813_0015"
down_revision: str | None = "20260813_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "underlying_intraday_bars",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("raw_event_id", sa.String(length=36), nullable=False),
        sa.Column("instrument_id", sa.String(length=36), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval_minutes", sa.Integer(), nullable=False),
        sa.Column("open", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("high", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("low", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("close", sa.Numeric(precision=28, scale=10), nullable=False),
        sa.Column("volume", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["instrument_id"], ["instruments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["raw_event_id"], ["raw_market_events.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "raw_event_id", "instrument_id", "started_at", "interval_minutes"
        ),
    )
    op.create_index(
        "ix_underlying_intraday_bars_raw_event_id",
        "underlying_intraday_bars",
        ["raw_event_id"],
    )
    op.create_index(
        "ix_underlying_intraday_bars_instrument_id",
        "underlying_intraday_bars",
        ["instrument_id"],
    )
    op.create_index(
        "ix_underlying_intraday_bars_started_at",
        "underlying_intraday_bars",
        ["started_at"],
    )
    op.create_index(
        "ix_intraday_bars_instrument_time_interval_raw_event",
        "underlying_intraday_bars",
        ["instrument_id", "started_at", "interval_minutes", "raw_event_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_intraday_bars_instrument_time_interval_raw_event",
        table_name="underlying_intraday_bars",
    )
    op.drop_index(
        "ix_underlying_intraday_bars_started_at",
        table_name="underlying_intraday_bars",
    )
    op.drop_index(
        "ix_underlying_intraday_bars_instrument_id",
        table_name="underlying_intraday_bars",
    )
    op.drop_index(
        "ix_underlying_intraday_bars_raw_event_id",
        table_name="underlying_intraday_bars",
    )
    op.drop_table("underlying_intraday_bars")
