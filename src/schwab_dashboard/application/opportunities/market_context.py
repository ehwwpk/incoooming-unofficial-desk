from __future__ import annotations

from decimal import Decimal

from schwab_dashboard.domain.market import UnderlyingDailyBar

HUNDRED = Decimal("100")


def session_return(bars: tuple[UnderlyingDailyBar, ...], sessions: int) -> Decimal | None:
    ordered = sorted(bars, key=lambda item: item.trade_date)
    if len(ordered) <= sessions:
        return None
    start = ordered[-(sessions + 1)].close
    end = ordered[-1].close
    return (end - start) / start * HUNDRED if start else None


def range_position(bars: tuple[UnderlyingDailyBar, ...], sessions: int = 60) -> Decimal | None:
    ordered = sorted(bars, key=lambda item: item.trade_date)[-sessions:]
    if not ordered:
        return None
    low = min(item.low for item in ordered)
    high = max(item.high for item in ordered)
    if high == low:
        return Decimal("50")
    return (ordered[-1].close - low) / (high - low) * HUNDRED
