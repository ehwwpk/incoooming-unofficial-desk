from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
