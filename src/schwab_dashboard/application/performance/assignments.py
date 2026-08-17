from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from schwab_dashboard.application.market_time import market_date
from schwab_dashboard.application.performance.models import AssignmentImpact

ZERO = Decimal("0")
STANDARD_SHARES = Decimal("100")


def calculate_assignment_impact(
    *,
    lifecycle_events: Sequence[dict[str, Any]],
    daily_bars: Sequence[dict[str, Any]],
    coverage_start: date | None,
    coverage_end: date | None,
) -> AssignmentImpact:
    assignments = tuple(
        row
        for row in lifecycle_events
        if str(row.get("event_type") or "").lower() == "assignment"
        and _inside(_date(row.get("occurred_at")), coverage_start, coverage_end)
    )
    calls = tuple(row for row in assignments if str(row.get("option_side")) == "call")
    puts = tuple(row for row in assignments if str(row.get("option_side")) == "put")
    call_contracts = sum((int(abs(_decimal(row.get("option_quantity")))) for row in calls), 0)
    put_contracts = sum((int(abs(_decimal(row.get("option_quantity")))) for row in puts), 0)
    called_away = sum((_shares(row) for row in calls), 0)
    acquired = sum((_shares(row) for row in puts), 0)

    references: list[Decimal] = []
    missing_reference = False
    if coverage_end is not None:
        latest_closes = _latest_closes(daily_bars, coverage_end)
        for row in calls:
            symbol = str(row.get("underlying_symbol") or "").upper()
            strike = row.get("strike")
            close = latest_closes.get(symbol)
            if strike is None or close is None:
                missing_reference = True
                continue
            references.append(
                max(ZERO, close - _decimal(strike)) * Decimal(_shares(row))
            )
    if not assignments:
        status = "no_assignments"
        note = "No short-option assignments fall inside the valued return window."
    elif missing_reference:
        status = "partial"
        note = (
            "Assignment counts are broker events. The period-end upside reference is partial "
            "because not every called-away symbol has a matching end close."
        )
    else:
        status = "ready"
        note = (
            "Called-away upside reference is strike-to-period-end close on assigned shares. "
            "It is opportunity context, not a realized loss, and ignores reinvestment."
        )
    return AssignmentImpact(
        status=status,
        assigned_call_contracts=call_contracts,
        called_away_shares=called_away,
        assigned_put_contracts=put_contracts,
        acquired_shares=acquired,
        period_end_upside_reference=(sum(references, ZERO) if references else None),
        method_note=note,
    )


def _latest_closes(rows: Sequence[dict[str, Any]], end: date) -> dict[str, Decimal]:
    latest: dict[str, tuple[date, Decimal]] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        day = row.get("trade_date")
        if not symbol or not isinstance(day, date) or day > end or row.get("close") is None:
            continue
        previous = latest.get(symbol)
        if previous is None or day > previous[0]:
            latest[symbol] = (day, _decimal(row["close"]))
    return {symbol: value for symbol, (_, value) in latest.items()}


def _shares(row: dict[str, Any]) -> int:
    stock_quantity = abs(_decimal(row.get("stock_quantity")))
    if stock_quantity:
        return int(stock_quantity)
    return int(abs(_decimal(row.get("option_quantity"))) * STANDARD_SHARES)


def _inside(value: date | None, start: date | None, end: date | None) -> bool:
    return value is not None and (start is None or value >= start) and (end is None or value <= end)


def _date(value: object) -> date | None:
    if isinstance(value, datetime):
        return market_date(value)
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)) if value else None


def _decimal(value: object) -> Decimal:
    return ZERO if value is None else Decimal(str(value))
