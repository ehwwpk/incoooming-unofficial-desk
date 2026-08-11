"""Add immutable daily underlying price bars for real chart reconstruction."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260810_0006"
down_revision: str | None = "20260810_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "underlying_daily_bars",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("raw_event_id", sa.String(length=36), nullable=False),
        sa.Column("instrument_id", sa.String(length=36), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(28, 10), nullable=False),
        sa.Column("high", sa.Numeric(28, 10), nullable=False),
        sa.Column("low", sa.Numeric(28, 10), nullable=False),
        sa.Column("close", sa.Numeric(28, 10), nullable=False),
        sa.Column("volume", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["raw_event_id"],
            ["raw_market_events.id"],
            name=op.f("fk_underlying_daily_bars_raw_event_id_raw_market_events"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name=op.f("fk_underlying_daily_bars_instrument_id_instruments"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_underlying_daily_bars")),
        sa.UniqueConstraint(
            "instrument_id",
            "trade_date",
            name=op.f("uq_underlying_daily_bars_instrument_id"),
        ),
    )
    for column in ("raw_event_id", "instrument_id", "trade_date"):
        op.create_index(
            op.f(f"ix_underlying_daily_bars_{column}"),
            "underlying_daily_bars",
            [column],
        )


def downgrade() -> None:
    op.drop_table("underlying_daily_bars")
