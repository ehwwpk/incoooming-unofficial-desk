from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ReturnPoint:
    date: date
    value: Decimal
    external_flow: Decimal
    daily_return_percent: Decimal | None
    cumulative_return_percent: Decimal | None
    quality: str


@dataclass(frozen=True, slots=True)
class ComparisonSeries:
    key: str
    label: str
    status: str
    return_percent: Decimal | None
    method_note: str
    points: tuple[ReturnPoint, ...]


@dataclass(frozen=True, slots=True)
class PerformanceComparison:
    methodology_version: str
    range_label: str
    coverage_start: date | None
    coverage_end: date | None
    external_flows_excluded: Decimal
    actual: ComparisonSeries
    shares_without_options: ComparisonSeries
    option_overlay: ComparisonSeries
    market_reference: ComparisonSeries
    warnings: tuple[str, ...]
