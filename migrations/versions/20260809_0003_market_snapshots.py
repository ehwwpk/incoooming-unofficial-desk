"""Add immutable raw market events and point-in-time quote snapshots."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260809_0003"
down_revision: str | None = "20260809_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "raw_market_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("external_event_key", sa.String(length=256), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("parser_version", sa.String(length=64), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_raw_market_events")),
        sa.UniqueConstraint(
            "source", "external_event_key", name=op.f("uq_raw_market_events_source")
        ),
    )
    op.create_index(op.f("ix_raw_market_events_source"), "raw_market_events", ["source"])
    op.create_index(op.f("ix_raw_market_events_observed_at"), "raw_market_events", ["observed_at"])

    op.create_table(
        "underlying_market_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("raw_event_id", sa.String(length=36), nullable=False),
        sa.Column("instrument_id", sa.String(length=36), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quote_quality", sa.String(length=16), nullable=False),
        sa.Column("mark_method", sa.String(length=16), nullable=False),
        sa.Column("bid", sa.Numeric(28, 10), nullable=True),
        sa.Column("ask", sa.Numeric(28, 10), nullable=True),
        sa.Column("last", sa.Numeric(28, 10), nullable=True),
        sa.Column("mark", sa.Numeric(28, 10), nullable=True),
        sa.Column("previous_close", sa.Numeric(28, 10), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["raw_event_id"],
            ["raw_market_events.id"],
            name=op.f("fk_underlying_market_snapshots_raw_event_id_raw_market_events"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name=op.f("fk_underlying_market_snapshots_instrument_id_instruments"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_underlying_market_snapshots")),
        sa.UniqueConstraint(
            "raw_event_id",
            "instrument_id",
            name=op.f("uq_underlying_market_snapshots_raw_event_id"),
        ),
    )
    for column in ("raw_event_id", "instrument_id", "observed_at", "quote_quality"):
        op.create_index(
            op.f(f"ix_underlying_market_snapshots_{column}"),
            "underlying_market_snapshots",
            [column],
        )

    op.create_table(
        "option_market_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("raw_event_id", sa.String(length=36), nullable=False),
        sa.Column("instrument_id", sa.String(length=36), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quote_quality", sa.String(length=16), nullable=False),
        sa.Column("mark_method", sa.String(length=16), nullable=False),
        sa.Column("bid", sa.Numeric(28, 10), nullable=True),
        sa.Column("ask", sa.Numeric(28, 10), nullable=True),
        sa.Column("last", sa.Numeric(28, 10), nullable=True),
        sa.Column("mark", sa.Numeric(28, 10), nullable=True),
        sa.Column("underlying_price", sa.Numeric(28, 10), nullable=True),
        sa.Column("implied_volatility", sa.Numeric(28, 10), nullable=True),
        sa.Column("delta", sa.Numeric(28, 10), nullable=True),
        sa.Column("gamma", sa.Numeric(28, 10), nullable=True),
        sa.Column("theta", sa.Numeric(28, 10), nullable=True),
        sa.Column("vega", sa.Numeric(28, 10), nullable=True),
        sa.Column("rho", sa.Numeric(28, 10), nullable=True),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("open_interest", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["raw_event_id"],
            ["raw_market_events.id"],
            name=op.f("fk_option_market_snapshots_raw_event_id_raw_market_events"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name=op.f("fk_option_market_snapshots_instrument_id_instruments"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_option_market_snapshots")),
        sa.UniqueConstraint(
            "raw_event_id",
            "instrument_id",
            name=op.f("uq_option_market_snapshots_raw_event_id"),
        ),
    )
    for column in ("raw_event_id", "instrument_id", "observed_at", "quote_quality"):
        op.create_index(
            op.f(f"ix_option_market_snapshots_{column}"),
            "option_market_snapshots",
            [column],
        )


def downgrade() -> None:
    op.drop_table("option_market_snapshots")
    op.drop_table("underlying_market_snapshots")
    op.drop_table("raw_market_events")
