from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class RadarMapPricePoint:
    trade_date: date
    close: Decimal
    x_percent: Decimal
    y_percent: Decimal


@dataclass(frozen=True, slots=True)
class RadarMapAxisLabel:
    price: Decimal
    y_percent: Decimal


@dataclass(frozen=True, slots=True)
class RadarMapIndicatorPoint:
    trade_date: date
    x_percent: Decimal
    rsi_14: Decimal | None
    macd: Decimal | None
    macd_signal: Decimal | None
    macd_histogram: Decimal | None


@dataclass(frozen=True, slots=True)
class RadarMapCandidate:
    sequence: int
    option_symbol: str
    strike: Decimal
    expiration_date: date
    days_to_expiration: int
    x_percent: Decimal
    y_percent: Decimal
    label_y_percent: Decimal
    effective_entry: Decimal | None
    effective_entry_y_percent: Decimal | None
    expected_move_low: Decimal | None
    expected_move_high: Decimal | None
    expected_move_low_y_percent: Decimal | None
    expected_move_high_y_percent: Decimal | None
    clears_all_rules: bool


@dataclass(frozen=True, slots=True)
class RadarExpirationMap:
    history_start: date
    as_of: date
    future_end: date
    minimum_price: Decimal
    maximum_price: Decimal
    spot: Decimal
    spot_x_percent: Decimal
    spot_y_percent: Decimal
    price_points: tuple[RadarMapPricePoint, ...]
    indicator_points: tuple[RadarMapIndicatorPoint, ...]
    axis_labels: tuple[RadarMapAxisLabel, ...]
    candidates: tuple[RadarMapCandidate, ...]
