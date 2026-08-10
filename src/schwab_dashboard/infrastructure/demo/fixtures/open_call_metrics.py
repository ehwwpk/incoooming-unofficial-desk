from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

D = Decimal


@dataclass(frozen=True, slots=True)
class OpenCallMetricFixture:
    symbol: str
    expires_on: date
    strike: Decimal
    bid_per_share: Decimal
    mark_per_share: Decimal
    ask_per_share: Decimal
    theta_per_share: Decimal
    implied_volatility_percent: Decimal
    delta: Decimal
    gamma: Decimal
    vega: Decimal
    volume: int
    open_interest: int


OPEN_CALL_METRICS = {
    (item.symbol, item.expires_on, item.strike): item
    for item in (
        OpenCallMetricFixture(
            "CVX",
            date(2026, 8, 14),
            D("195"),
            D("2.40"),
            D("2.50"),
            D("2.60"),
            D("-0.080"),
            D("24.5"),
            D("0.31"),
            D("0.052"),
            D("0.061"),
            418,
            2201,
        ),
        OpenCallMetricFixture(
            "CVX",
            date(2026, 8, 21),
            D("205"),
            D("1.00"),
            D("1.10"),
            D("1.20"),
            D("-0.050"),
            D("24.0"),
            D("0.19"),
            D("0.031"),
            D("0.089"),
            206,
            1644,
        ),
        OpenCallMetricFixture(
            "CVX",
            date(2026, 9, 18),
            D("215"),
            D("1.10"),
            D("1.20"),
            D("1.30"),
            D("-0.035"),
            D("23.8"),
            D("0.16"),
            D("0.018"),
            D("0.142"),
            151,
            3120,
        ),
        OpenCallMetricFixture(
            "KTOS",
            date(2026, 8, 28),
            D("75"),
            D("0.60"),
            D("0.70"),
            D("0.80"),
            D("-0.045"),
            D("58.6"),
            D("0.18"),
            D("0.026"),
            D("0.071"),
            338,
            1908,
        ),
        OpenCallMetricFixture(
            "KTOS",
            date(2026, 9, 25),
            D("90"),
            D("0.50"),
            D("0.60"),
            D("0.70"),
            D("-0.020"),
            D("57.9"),
            D("0.10"),
            D("0.011"),
            D("0.111"),
            104,
            876,
        ),
        OpenCallMetricFixture(
            "URNM",
            date(2026, 9, 18),
            D("67.5"),
            D("0.87"),
            D("0.92"),
            D("0.97"),
            D("-0.036"),
            D("41.2"),
            D("0.20"),
            D("0.021"),
            D("0.106"),
            92,
            1288,
        ),
    )
}
