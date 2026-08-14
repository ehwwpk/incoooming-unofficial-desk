from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from schwab_dashboard.application.performance.flows import movement_date
from schwab_dashboard.application.performance.models import ComparisonSeries, ReturnPoint

ZERO = Decimal("0")
HUNDRED = Decimal("100")


def build_executed_option_overlay(
    *,
    executions: Sequence[dict[str, Any]],
    actual_points: Sequence[ReturnPoint],
) -> ComparisonSeries:
    if not actual_points or actual_points[0].value == ZERO:
        return _unavailable("A starting net-liquidation value is required.")
    start, end = actual_points[0].date, actual_points[-1].date
    cash_by_day: dict[date, Decimal] = defaultdict(lambda: ZERO)
    for row in executions:
        if str(row.get("asset_type") or "").lower() != "option":
            continue
        day = movement_date(row.get("occurred_at"))
        if day is None or not start <= day <= end:
            continue
        if (str(row.get("side")), str(row.get("position_effect"))) not in {
            ("sell", "opening"),
            ("buy", "closing"),
        }:
            continue
        cash_by_day[day] += Decimal(str(row.get("net_cash") or "0"))
    if not cash_by_day:
        return _unavailable("No normalized short-option cash executions fall inside coverage.")
    capital = actual_points[0].value
    cumulative = ZERO
    points: list[ReturnPoint] = []
    for point in actual_points:
        day_cash = cash_by_day[point.date]
        cumulative += day_cash
        points.append(
            ReturnPoint(
                date=point.date,
                value=cumulative,
                external_flow=ZERO,
                daily_return_percent=day_cash / capital * HUNDRED,
                cumulative_return_percent=cumulative / capital * HUNDRED,
                quality="executed_cash_only",
            )
        )
    return ComparisonSeries(
        key="option_overlay",
        label="Executed option cash",
        status="cash_only",
        return_percent=points[-1].cumulative_return_percent,
        method_note=(
            "Opening option credits less executed closing debits, divided by starting net "
            "liquidation. Open marks and foregone stock upside are not included."
        ),
        points=tuple(points),
    )


def _unavailable(note: str) -> ComparisonSeries:
    return ComparisonSeries(
        key="option_overlay",
        label="Executed option cash",
        status="not_available",
        return_percent=None,
        method_note=note,
        points=(),
    )
