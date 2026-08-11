from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from schwab_dashboard.infrastructure.database.tables.base import Base, utc_now


class AccountTable(Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("source", "external_account_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="schwab")
    external_account_key: Mapped[str] = mapped_column(String(256), nullable=False)
    account_mask: Mapped[str] = mapped_column(String(32), nullable=False)
    account_type: Mapped[str] = mapped_column(String(64), nullable=False)
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class PositionSnapshotTable(Base):
    __tablename__ = "position_snapshots"
    __table_args__ = (UniqueConstraint("sync_run_id", "account_id", "instrument_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    account_id: Mapped[str] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sync_run_id: Mapped[str] = mapped_column(
        ForeignKey("sync_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    raw_event_id: Mapped[str] = mapped_column(
        ForeignKey("raw_broker_events.id", ondelete="RESTRICT"), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    instrument_key: Mapped[str] = mapped_column(String(256), nullable=False)
    symbol: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    long_quantity: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    short_quantity: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    average_price: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    market_value: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    day_profit_loss: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    day_profit_loss_percent: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    description: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    underlying_symbol: Mapped[str | None] = mapped_column(String(64), index=True)
    option_type: Mapped[str | None] = mapped_column(String(16), index=True)
    expiration_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    strike: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    long_open_profit_loss: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    short_open_profit_loss: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class AccountBalanceSnapshotTable(Base):
    __tablename__ = "account_balance_snapshots"
    __table_args__ = (UniqueConstraint("sync_run_id", "account_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    account_id: Mapped[str] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sync_run_id: Mapped[str] = mapped_column(
        ForeignKey("sync_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    raw_event_id: Mapped[str] = mapped_column(
        ForeignKey("raw_broker_events.id", ondelete="RESTRICT"), nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    liquidation_value: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    initial_liquidation_value: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    equity: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    cash_balance: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    money_market_fund: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    margin_balance: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    buying_power: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    available_funds: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    maintenance_requirement: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    long_market_value: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    short_market_value: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    long_option_market_value: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    short_option_market_value: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    is_portfolio_margin: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    is_intraday_margin: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
