from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from schwab_dashboard.infrastructure.database.tables.base import Base, utc_now


class RadarPolicyTable(Base):
    __tablename__ = "radar_policies"
    __table_args__ = (UniqueConstraint("symbol", "mode"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    minimum_dte: Mapped[int] = mapped_column(Integer, nullable=False)
    maximum_dte: Mapped[int] = mapped_column(Integer, nullable=False)
    minimum_annualized_rate_percent: Mapped[Decimal] = mapped_column(
        Numeric(28, 10), nullable=False
    )
    minimum_strike: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    minimum_strike_distance_percent: Mapped[Decimal] = mapped_column(
        Numeric(28, 10), nullable=False
    )
    maximum_effective_entry: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    maximum_spread_percent: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    minimum_open_interest: Mapped[int] = mapped_column(Integer, nullable=False)
    minimum_volume: Mapped[int] = mapped_column(Integer, nullable=False)
    maximum_quote_age_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    allowed_contracts: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved_cash: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    maximum_five_day_move_percent: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class RadarSavedSymbolTable(Base):
    __tablename__ = "radar_saved_symbols"
    __table_args__ = (UniqueConstraint("source", "symbol"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    saved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RadarLookupRunTable(Base):
    __tablename__ = "radar_lookup_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    policy_version: Mapped[int | None] = mapped_column(Integer)
    projection: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(String(512))


class RadarCandidateSnapshotTable(Base):
    __tablename__ = "radar_candidate_snapshots"
    __table_args__ = (UniqueConstraint("lookup_id", "option_symbol"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    lookup_id: Mapped[str] = mapped_column(
        ForeignKey("radar_lookup_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    option_symbol: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    frontier_label: Mapped[str | None] = mapped_column(String(32))
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    gates: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
