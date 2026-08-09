from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from schwab_dashboard.infrastructure.database.tables.base import Base, utc_now


class ExecutionTable(Base):
    __tablename__ = "executions"
    __table_args__ = (UniqueConstraint("source", "account_id", "external_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instrument_id: Mapped[str] = mapped_column(
        ForeignKey("instruments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    raw_event_id: Mapped[str] = mapped_column(
        ForeignKey("raw_broker_events.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    external_key: Mapped[str] = mapped_column(String(256), nullable=False)
    order_external_key: Mapped[str | None] = mapped_column(String(256), index=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    position_effect: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    fees: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    net_cash: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CashMovementTable(Base):
    __tablename__ = "cash_movements"
    __table_args__ = (UniqueConstraint("source", "account_id", "external_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    instrument_id: Mapped[str | None] = mapped_column(
        ForeignKey("instruments.id", ondelete="RESTRICT"), index=True
    )
    raw_event_id: Mapped[str] = mapped_column(
        ForeignKey("raw_broker_events.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    external_key: Mapped[str] = mapped_column(String(256), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    movement_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class OptionLifecycleEventTable(Base):
    __tablename__ = "option_lifecycle_events"
    __table_args__ = (UniqueConstraint("source", "account_id", "external_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    option_instrument_id: Mapped[str] = mapped_column(
        ForeignKey("instruments.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    stock_instrument_id: Mapped[str | None] = mapped_column(
        ForeignKey("instruments.id", ondelete="RESTRICT"), index=True
    )
    raw_event_id: Mapped[str] = mapped_column(
        ForeignKey("raw_broker_events.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    external_key: Mapped[str] = mapped_column(String(256), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    option_quantity: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    stock_quantity: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    cash_amount: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
