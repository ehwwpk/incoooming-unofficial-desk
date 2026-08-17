from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from schwab_dashboard.application.market_time import market_date
from schwab_dashboard.application.performance.flows import external_flow_on
from schwab_dashboard.application.performance.models import ReturnPoint

ZERO = Decimal("0")
HUNDRED = Decimal("100")


def build_time_weighted_returns(
    balance_history: Sequence[dict[str, Any]],
    cash_movements: Sequence[dict[str, Any]],
) -> tuple[ReturnPoint, ...]:
    """Build one aggregate daily valuation and chain deposit-neutral returns."""
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
        account = str(row.get("account_mask") or "ACCOUNT")
        existing = grouped[day].get(account)
        if existing is None or existing["observed_at"] <= observed_at:
            grouped[day][account] = row

    points: list[ReturnPoint] = []
    cumulative_factor = Decimal("1")
    previous_value: Decimal | None = None
    for day, accounts in sorted(grouped.items()):
        rows = tuple(accounts.values())
        current_values = [_optional_decimal(row.get("liquidation_value")) for row in rows]
        if not current_values or any(value is None for value in current_values):
            continue
        value = sum((item for item in current_values if item is not None), ZERO)
        initial_values = [
            _optional_decimal(row.get("initial_liquidation_value")) for row in rows
        ]
        flow = external_flow_on(cash_movements, day)
        daily_return: Decimal | None = None
        quality = "observed_anchor"
        # The first stored value is the comparison anchor. Counting Schwab's
        # opening balance on that first day would make the managed series begin
        # before the frozen-share and market series, overstating management's
        # difference by one unmatched session.
        if previous_value is not None:
            opening = (
                sum((item for item in initial_values if item is not None), ZERO)
                if initial_values and all(item is not None for item in initial_values)
                else previous_value
            )
        else:
            opening = None
        if opening is not None and opening != ZERO:
            daily_return = (value - opening - flow) / opening * HUNDRED
            cumulative_factor *= Decimal("1") + daily_return / HUNDRED
            quality = (
                "broker_opening"
                if all(item is not None for item in initial_values)
                else "linked"
            )
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
    return tuple(points)


def _optional_decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))
