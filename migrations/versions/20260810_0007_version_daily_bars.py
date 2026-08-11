"""Retain revisions of historical candles instead of blocking corrected market data."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260810_0007"
down_revision: str | None = "20260810_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("underlying_daily_bars") as batch:
        batch.drop_constraint("uq_underlying_daily_bars_instrument_id", type_="unique")
        batch.create_unique_constraint(
            "uq_underlying_daily_bars_raw_event_id",
            ["raw_event_id", "instrument_id", "trade_date"],
        )


def downgrade() -> None:
    with op.batch_alter_table("underlying_daily_bars") as batch:
        batch.drop_constraint("uq_underlying_daily_bars_raw_event_id", type_="unique")
        batch.create_unique_constraint(
            "uq_underlying_daily_bars_instrument_id",
            ["instrument_id", "trade_date"],
        )
