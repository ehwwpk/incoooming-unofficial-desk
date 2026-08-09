from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, Date, DateTime, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from schwab_dashboard.infrastructure.database.tables.base import Base, utc_now


class InstrumentTable(Base):
    __tablename__ = "instruments"
    __table_args__ = (UniqueConstraint("source", "external_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    external_key: Mapped[str] = mapped_column(String(256), nullable=False)
    symbol: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(512))
    underlying_symbol: Mapped[str | None] = mapped_column(String(128), index=True)
    option_side: Mapped[str | None] = mapped_column(String(8))
    expiration_date: Mapped[date | None] = mapped_column(Date())
    strike: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    contract_multiplier: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    deliverable: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
