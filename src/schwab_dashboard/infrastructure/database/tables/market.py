from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from schwab_dashboard.infrastructure.database.tables.base import Base, utc_now


class RawMarketEventTable(Base):
    __tablename__ = "raw_market_events"
    __table_args__ = (UniqueConstraint("source", "external_event_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    external_event_key: Mapped[str] = mapped_column(String(256), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    parser_version: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class UnderlyingMarketSnapshotTable(Base):
    __tablename__ = "underlying_market_snapshots"
    __table_args__ = (UniqueConstraint("raw_event_id", "instrument_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    raw_event_id: Mapped[str] = mapped_column(
        ForeignKey("raw_market_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instrument_id: Mapped[str] = mapped_column(
        ForeignKey("instruments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    quote_quality: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    mark_method: Mapped[str] = mapped_column(String(16), nullable=False)
    bid: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    ask: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    last: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    mark: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    previous_close: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class OptionMarketSnapshotTable(Base):
    __tablename__ = "option_market_snapshots"
    __table_args__ = (UniqueConstraint("raw_event_id", "instrument_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    raw_event_id: Mapped[str] = mapped_column(
        ForeignKey("raw_market_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instrument_id: Mapped[str] = mapped_column(
        ForeignKey("instruments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    quote_quality: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    mark_method: Mapped[str] = mapped_column(String(16), nullable=False)
    bid: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    ask: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    last: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    mark: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    underlying_price: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    implied_volatility: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    delta: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    gamma: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    theta: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    vega: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    rho: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    volume: Mapped[int | None] = mapped_column(Integer)
    open_interest: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class UnderlyingDailyBarTable(Base):
    __tablename__ = "underlying_daily_bars"
    __table_args__ = (UniqueConstraint("raw_event_id", "instrument_id", "trade_date"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    raw_event_id: Mapped[str] = mapped_column(
        ForeignKey("raw_market_events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instrument_id: Mapped[str] = mapped_column(
        ForeignKey("instruments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    trade_date: Mapped[date] = mapped_column(Date(), nullable=False, index=True)
    open: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    volume: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
