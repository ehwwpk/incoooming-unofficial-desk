"""Add broker-neutral instruments and atomic ledger activity."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260809_0002"
down_revision: str | None = "20260807_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "instruments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("external_key", sa.String(length=256), nullable=False),
        sa.Column("symbol", sa.String(length=128), nullable=False),
        sa.Column("asset_type", sa.String(length=32), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.Column("underlying_symbol", sa.String(length=128), nullable=True),
        sa.Column("option_side", sa.String(length=8), nullable=True),
        sa.Column("expiration_date", sa.Date(), nullable=True),
        sa.Column("strike", sa.Numeric(28, 10), nullable=True),
        sa.Column("contract_multiplier", sa.Numeric(28, 10), nullable=True),
        sa.Column("deliverable", sa.JSON(), nullable=True),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_instruments")),
        sa.UniqueConstraint("source", "external_key", name=op.f("uq_instruments_source")),
    )
    op.create_index(op.f("ix_instruments_asset_type"), "instruments", ["asset_type"])
    op.create_index(op.f("ix_instruments_underlying_symbol"), "instruments", ["underlying_symbol"])
    op.create_index(op.f("ix_instruments_source"), "instruments", ["source"])
    op.create_index(op.f("ix_instruments_symbol"), "instruments", ["symbol"])

    op.create_table(
        "executions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("instrument_id", sa.String(length=36), nullable=False),
        sa.Column("raw_event_id", sa.String(length=36), nullable=False),
        sa.Column("external_key", sa.String(length=256), nullable=False),
        sa.Column("order_external_key", sa.String(length=256), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("position_effect", sa.String(length=16), nullable=False),
        sa.Column("quantity", sa.Numeric(28, 10), nullable=False),
        sa.Column("price", sa.Numeric(28, 10), nullable=False),
        sa.Column("gross_amount", sa.Numeric(28, 10), nullable=False),
        sa.Column("fees", sa.Numeric(28, 10), nullable=False),
        sa.Column("net_cash", sa.Numeric(28, 10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_executions_account_id_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name=op.f("fk_executions_instrument_id_instruments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["raw_event_id"],
            ["raw_broker_events.id"],
            name=op.f("fk_executions_raw_event_id_raw_broker_events"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_executions")),
        sa.UniqueConstraint(
            "source", "account_id", "external_key", name=op.f("uq_executions_source")
        ),
    )
    for column in (
        "source",
        "account_id",
        "instrument_id",
        "raw_event_id",
        "order_external_key",
        "occurred_at",
    ):
        op.create_index(op.f(f"ix_executions_{column}"), "executions", [column])

    op.create_table(
        "cash_movements",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("instrument_id", sa.String(length=36), nullable=True),
        sa.Column("raw_event_id", sa.String(length=36), nullable=False),
        sa.Column("external_key", sa.String(length=256), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("movement_type", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Numeric(28, 10), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_cash_movements_account_id_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["instrument_id"],
            ["instruments.id"],
            name=op.f("fk_cash_movements_instrument_id_instruments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["raw_event_id"],
            ["raw_broker_events.id"],
            name=op.f("fk_cash_movements_raw_event_id_raw_broker_events"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cash_movements")),
        sa.UniqueConstraint(
            "source", "account_id", "external_key", name=op.f("uq_cash_movements_source")
        ),
    )
    for column in (
        "source",
        "account_id",
        "instrument_id",
        "raw_event_id",
        "occurred_at",
        "movement_type",
    ):
        op.create_index(op.f(f"ix_cash_movements_{column}"), "cash_movements", [column])

    op.create_table(
        "option_lifecycle_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("option_instrument_id", sa.String(length=36), nullable=False),
        sa.Column("stock_instrument_id", sa.String(length=36), nullable=True),
        sa.Column("raw_event_id", sa.String(length=36), nullable=False),
        sa.Column("external_key", sa.String(length=256), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_type", sa.String(length=16), nullable=False),
        sa.Column("option_quantity", sa.Numeric(28, 10), nullable=False),
        sa.Column("stock_quantity", sa.Numeric(28, 10), nullable=True),
        sa.Column("cash_amount", sa.Numeric(28, 10), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["accounts.id"],
            name=op.f("fk_option_lifecycle_events_account_id_accounts"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["option_instrument_id"],
            ["instruments.id"],
            name=op.f("fk_option_lifecycle_events_option_instrument_id_instruments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["stock_instrument_id"],
            ["instruments.id"],
            name=op.f("fk_option_lifecycle_events_stock_instrument_id_instruments"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["raw_event_id"],
            ["raw_broker_events.id"],
            name=op.f("fk_option_lifecycle_events_raw_event_id_raw_broker_events"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_option_lifecycle_events")),
        sa.UniqueConstraint(
            "source",
            "account_id",
            "external_key",
            name=op.f("uq_option_lifecycle_events_source"),
        ),
    )
    for column in (
        "source",
        "account_id",
        "option_instrument_id",
        "stock_instrument_id",
        "raw_event_id",
        "occurred_at",
        "event_type",
    ):
        op.create_index(
            op.f(f"ix_option_lifecycle_events_{column}"), "option_lifecycle_events", [column]
        )


def downgrade() -> None:
    op.drop_table("option_lifecycle_events")
    op.drop_table("cash_movements")
    op.drop_table("executions")
    op.drop_table("instruments")
