from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from schwab_dashboard.application.ports.ledger import InstrumentRepository
from schwab_dashboard.domain.market import (
    OptionMarketSnapshot,
    UnderlyingDailyBar,
    UnderlyingIntradayBar,
    UnderlyingMarketSnapshot,
)


class RawMarketEventRepository(Protocol):
    def add(
        self,
        *,
        source: str,
        external_event_key: str,
        observed_at: datetime,
        parser_version: str,
        payload: dict[str, Any],
    ) -> str: ...


@dataclass(frozen=True, slots=True)
class UnderlyingMarketSnapshotWrite:
    raw_event_id: str
    instrument_id: str
    snapshot: UnderlyingMarketSnapshot


@dataclass(frozen=True, slots=True)
class OptionMarketSnapshotWrite:
    raw_event_id: str
    instrument_id: str
    snapshot: OptionMarketSnapshot


@dataclass(frozen=True, slots=True)
class UnderlyingDailyBarWrite:
    raw_event_id: str
    instrument_id: str
    bar: UnderlyingDailyBar


@dataclass(frozen=True, slots=True)
class UnderlyingIntradayBarWrite:
    raw_event_id: str
    instrument_id: str
    bar: UnderlyingIntradayBar


class UnderlyingMarketSnapshotRepository(Protocol):
    def add(self, item: UnderlyingMarketSnapshotWrite) -> str: ...


class OptionMarketSnapshotRepository(Protocol):
    def add(self, item: OptionMarketSnapshotWrite) -> str: ...


class UnderlyingDailyBarRepository(Protocol):
    def add(self, item: UnderlyingDailyBarWrite) -> str: ...


class UnderlyingIntradayBarRepository(Protocol):
    def add(self, item: UnderlyingIntradayBarWrite) -> str: ...


class MarketUnitOfWork(Protocol):
    instruments: InstrumentRepository
    raw_market_events: RawMarketEventRepository
    underlying_market_snapshots: UnderlyingMarketSnapshotRepository
    option_market_snapshots: OptionMarketSnapshotRepository
    underlying_daily_bars: UnderlyingDailyBarRepository
    underlying_intraday_bars: UnderlyingIntradayBarRepository

    def __enter__(self) -> MarketUnitOfWork: ...

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


MarketUnitOfWorkFactory = Callable[[], MarketUnitOfWork]
