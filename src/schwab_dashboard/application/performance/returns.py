from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from schwab_dashboard.application.market_time import market_date
from schwab_dashboard.application.performance.flows import (
    external_flow_between,
    external_flow_on,
)
from schwab_dashboard.application.performance.models import ReturnPoint
from schwab_dashboard.application.performance.sessions import MarketCalendar

ZERO = Decimal("0")
HUNDRED = Decimal("100")


def build_time_weighted_returns(
    balance_history: Sequence[dict[str, Any]],
    cash_movements: Sequence[dict[str, Any]],
    *,
    calendar: MarketCalendar | None = None,
) -> tuple[ReturnPoint, ...]:
    """Build one aggregate daily valuation and chain deposit-neutral returns.

    Only trading sessions are chained. Brokers keep publishing net-liquidation
    snapshots over weekends and holidays as marks and cash sweeps settle, and
    chaining those drifts as return days both invents performance the market
    never delivered and leaves the managed series with dates no price-based
    comparison series can ever match.
    """
    grouped: dict[date, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in balance_history:
        observed_at = row.get("observed_at")
        if observed_at is None:
            continue
        # Snapshots are persisted as normalized UTC instants.  A Friday-evening
        # sync is already Saturday in UTC, but it still belongs to Friday's U.S.
        # market session.  Grouping on ``datetime.date()`` double-counted that
        # same broker opening balance as a second return day.
        day = market_date(observed_at)
        if calendar is not None and not calendar.is_session(day):
            continue
        account = str(row.get("account_mask") or "ACCOUNT")
        existing = grouped[day].get(account)
        if existing is None or existing["observed_at"] <= observed_at:
            grouped[day][account] = row

    points: list[ReturnPoint] = []
    cumulative_factor = Decimal("1")
    previous_value: Decimal | None = None
    previous_day: date | None = None
    for day, accounts in sorted(grouped.items()):
        rows = tuple(accounts.values())
        current_values = [_optional_decimal(row.get("liquidation_value")) for row in rows]
        if not current_values or any(value is None for value in current_values):
            continue
        value = sum((item for item in current_values if item is not None), ZERO)
        # The first stored value is the comparison anchor. Counting the broker's
        # opening balance on that first day would make the managed series begin
        # before the frozen-share and market series, overstating management's
        # difference by one unmatched session.
        flow = (
            external_flow_on(cash_movements, day)
            if previous_day is None
            else external_flow_between(cash_movements, after=previous_day, through=day)
        )
        daily_return: Decimal | None = None
        quality = "observed_anchor"
        # Chain against the previous stored valuation rather than the broker's
        # stated opening balance. The two disagree whenever overnight
        # processing lands between the last sync and the next session, and
        # measuring from the broker's opening silently discards the P/L in that
        # seam instead of attributing it to anyone.
        if previous_value is not None and previous_value != ZERO:
            daily_return = (value - previous_value - flow) / previous_value * HUNDRED
            cumulative_factor *= Decimal("1") + daily_return / HUNDRED
            quality = "linked"
        points.append(
            ReturnPoint(
                date=day,
                value=value,
                external_flow=flow,
                daily_return_percent=daily_return,
                cumulative_return_percent=(
                    (cumulative_factor - Decimal("1")) * HUNDRED
                    if daily_return is not None
                    else None
                ),
                quality=quality,
            )
        )
        previous_value = value
        previous_day = day
    return tuple(points)


def _optional_decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))
