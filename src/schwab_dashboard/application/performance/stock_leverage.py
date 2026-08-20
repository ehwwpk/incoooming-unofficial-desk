from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from schwab_dashboard.application.market_time import market_date

ZERO = Decimal("0")


def option_market_value(row: Mapping[str, Any]) -> Decimal:
    """Signed option marks as stored. Shorts are typically negative."""

    return _decimal(row.get("long_option_market_value")) + _decimal(
        row.get("short_option_market_value")
    )


def stock_capital(row: Mapping[str, Any]) -> Decimal | None:
    nl = _optional(row.get("liquidation_value"))
    if nl is None:
        return None
    return nl - option_market_value(row)


def stock_leverage_ratio(row: Mapping[str, Any]) -> Decimal | None:
    """Long stock over stock-ex-overlay capital. Maintenance is not in this ratio."""

    long_market_value = _optional(row.get("long_market_value"))
    capital = stock_capital(row)
    if long_market_value is None or capital is None:
        return None
    if long_market_value <= ZERO or capital <= ZERO:
        return None
    return long_market_value / capital


def leverage_on(
    balance_history: Sequence[Mapping[str, Any]],
    day: date,
) -> Decimal | None:
    """Latest same-session snapshot that can form L_t, or none."""

    chosen: Mapping[str, Any] | None = None
    for row in balance_history:
        observed = row.get("observed_at")
        if observed is None:
            continue
        if _as_day(observed) != day:
            continue
        if chosen is None or _as_instant(chosen.get("observed_at")) <= _as_instant(observed):
            chosen = row
    if chosen is None:
        return None
    return stock_leverage_ratio(chosen)


def _optional(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _decimal(value: object) -> Decimal:
    return ZERO if value is None else Decimal(str(value))


def _as_day(value: object) -> date | None:
    if isinstance(value, datetime):
        return market_date(value)
    if isinstance(value, date):
        return value
    return None


def _as_instant(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    raise TypeError("balance snapshot is missing observed_at")
