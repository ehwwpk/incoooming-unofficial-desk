from __future__ import annotations

from datetime import date
from decimal import Decimal
from math import sqrt

HUNDRED = Decimal("100")
YEAR_DAYS = Decimal("365")


def midpoint(bid: Decimal, ask: Decimal) -> Decimal:
    return (bid + ask) / Decimal("2")


def spread_percent(bid: Decimal, ask: Decimal) -> Decimal:
    middle = midpoint(bid, ask)
    return (ask - bid) / middle * HUNDRED if middle > 0 else Decimal("0")


def days_to_expiration(expiration: date, *, as_of: date) -> int:
    return max(0, (expiration - as_of).days)


def normalize_implied_volatility(value: Decimal | None) -> Decimal | None:
    if value is None or value <= 0:
        return None
    return value / HUNDRED if value > Decimal("3") else value


def expected_move(
    spot: Decimal,
    implied_volatility: Decimal | None,
    dte: int,
) -> Decimal | None:
    normalized = normalize_implied_volatility(implied_volatility)
    if normalized is None or spot <= 0 or dte <= 0:
        return None
    scale = Decimal(str(sqrt(float(Decimal(dte) / YEAR_DAYS))))
    return spot * normalized * scale


def simple_annualized_rate(
    *, premium_per_share: Decimal, capital_per_share: Decimal, dte: int
) -> Decimal:
    if premium_per_share <= 0 or capital_per_share <= 0 or dte <= 0:
        return Decimal("0")
    return premium_per_share / capital_per_share * YEAR_DAYS / Decimal(dte) * HUNDRED


def bid_credit_per_calendar_day(*, premium_per_contract: Decimal, dte: int) -> Decimal:
    """Return a straight-line planning pace, not option theta or earned income."""

    if premium_per_contract <= 0 or dte <= 0:
        return Decimal("0")
    return premium_per_contract / Decimal(dte)
