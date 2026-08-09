from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from schwab_dashboard.domain.instruments import InstrumentRecord
from schwab_dashboard.domain.validation import (
    require_aware,
    require_optional_non_negative,
    require_text,
)


class QuoteQuality(StrEnum):
    COMPLETE = "complete"
    ONE_SIDED = "one_sided"
    CROSSED = "crossed"
    NO_MARKET = "no_market"
    UNKNOWN = "unknown"


class MarkMethod(StrEnum):
    BROKER = "broker"
    MIDPOINT = "midpoint"
    LAST = "last"
    MODEL = "model"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class InstrumentRef:
    source: str
    external_key: str

    def __post_init__(self) -> None:
        require_text(self.source, "source")
        require_text(self.external_key, "external_key")


@dataclass(frozen=True, slots=True)
class UnderlyingMarketSnapshot:
    instrument: InstrumentRef
    observed_at: datetime
    quote_quality: QuoteQuality
    mark_method: MarkMethod
    bid: Decimal | None = None
    ask: Decimal | None = None
    last: Decimal | None = None
    mark: Decimal | None = None
    previous_close: Decimal | None = None

    def __post_init__(self) -> None:
        require_aware(self.observed_at, "observed_at")
        for name in ("bid", "ask", "last", "mark", "previous_close"):
            require_optional_non_negative(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class OptionMarketSnapshot:
    instrument: InstrumentRef
    observed_at: datetime
    quote_quality: QuoteQuality
    mark_method: MarkMethod
    bid: Decimal | None = None
    ask: Decimal | None = None
    last: Decimal | None = None
    mark: Decimal | None = None
    underlying_price: Decimal | None = None
    implied_volatility: Decimal | None = None
    delta: Decimal | None = None
    gamma: Decimal | None = None
    theta: Decimal | None = None
    vega: Decimal | None = None
    rho: Decimal | None = None
    volume: int | None = None
    open_interest: int | None = None

    def __post_init__(self) -> None:
        require_aware(self.observed_at, "observed_at")
        for name in ("bid", "ask", "last", "mark", "underlying_price", "implied_volatility"):
            require_optional_non_negative(getattr(self, name), name)
        for name in ("volume", "open_interest"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must be non-negative")


@dataclass(frozen=True, slots=True)
class MarketObservationBatch:
    source: str
    external_event_key: str
    observed_at: datetime
    parser_version: str
    raw_payload: dict[str, Any]
    instruments: tuple[InstrumentRecord, ...] = ()
    underlying_snapshots: tuple[UnderlyingMarketSnapshot, ...] = ()
    option_snapshots: tuple[OptionMarketSnapshot, ...] = ()

    def __post_init__(self) -> None:
        require_text(self.source, "source")
        require_text(self.external_event_key, "external_event_key")
        require_text(self.parser_version, "parser_version")
        require_aware(self.observed_at, "observed_at")
