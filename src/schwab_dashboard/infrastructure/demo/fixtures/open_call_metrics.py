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
    mark_per_share: Decimal
    theta_per_share: Decimal


OPEN_CALL_METRICS = {
    (item.symbol, item.expires_on, item.strike): item
    for item in (
        OpenCallMetricFixture("CVX", date(2026, 9, 4), D("235"), D("1.20"), D("-0.040")),
        OpenCallMetricFixture("CVX", date(2026, 9, 18), D("225"), D("1.80"), D("-0.035")),
        OpenCallMetricFixture("KTOS", date(2026, 9, 18), D("75"), D("3.30"), D("-0.065")),
        OpenCallMetricFixture("KTOS", date(2026, 9, 18), D("82.5"), D("1.10"), D("-0.045")),
        OpenCallMetricFixture("URNM", date(2026, 9, 18), D("67.5"), D("0.92"), D("-0.036")),
    )
}
