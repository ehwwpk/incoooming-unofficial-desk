from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from schwab_dashboard.application.market_time import ledger_market_date
from schwab_dashboard.application.option_lifecycle import (
    delivered_share_quantity,
    lifecycle_event_type,
    option_contracts,
    option_side,
)
from schwab_dashboard.application.performance.models import AssignmentImpact

ZERO = Decimal("0")


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
        if lifecycle_event_type(row.get("event_type")) == "assignment"
        and _inside(_date(row.get("occurred_at")), coverage_start, coverage_end)
    )
    calls = tuple(row for row in assignments if option_side(row.get("option_side")) == "call")
    puts = tuple(row for row in assignments if option_side(row.get("option_side")) == "put")
    unknown = tuple(row for row in assignments if option_side(row.get("option_side")) is None)
    call_contracts = sum((option_contracts(row) for row in calls), 0)
    put_contracts = sum((option_contracts(row) for row in puts), 0)
    unknown_contracts = sum((option_contracts(row) for row in unknown), 0)
    called_away = sum((delivered_share_quantity(row) for row in calls), ZERO)
    acquired = sum((delivered_share_quantity(row) for row in puts), ZERO)

    references: list[Decimal] = []
    reference_dates: list[date] = []
    missing_reference = False
    if coverage_end is not None:
        latest_closes = _latest_closes(daily_bars, coverage_end)
        for row in calls:
            symbol = str(row.get("underlying_symbol") or "").upper()
            strike = row.get("strike")
            close_record = latest_closes.get(symbol)
            if strike is None or close_record is None:
                missing_reference = True
                continue
            close_date, close = close_record
            references.append(max(ZERO, close - _decimal(strike)) * delivered_share_quantity(row))
            reference_dates.append(close_date)
    elif calls:
        missing_reference = True

    reference_as_of = min(reference_dates) if reference_dates else None
    reference_age_days = (
        (coverage_end - reference_as_of).days
        if coverage_end is not None and reference_as_of is not None
        else None
    )
    if not calls:
        reference_quality = "not_applicable"
    elif not references:
        reference_quality = "unavailable"
    elif missing_reference:
        reference_quality = "partial"
    elif reference_age_days:
        reference_quality = "stale"
    else:
        reference_quality = "exact"

    if not assignments:
        status = "no_assignments"
        note = "No short-option assignments fall inside the valued return window."
    elif unknown or reference_quality in {"unavailable", "partial", "stale"}:
        status = "partial"
        notes = ["Assignment counts are broker events."]
        if unknown:
            notes.append(
                f"{len(unknown)} assignment event(s) have no recognized call/put side and are "
                "excluded from directional share totals."
            )
        if reference_quality == "unavailable":
            notes.append("No complete strike/close input is available for assigned calls.")
        elif reference_quality == "partial":
            notes.append("The upside reference omits assigned calls missing a strike or close.")
        elif reference_quality == "stale":
            notes.append(
                f"The oldest close used is from {reference_as_of:%b %d, %Y}, "
                f"{reference_age_days} calendar day(s) before the return-window end."
            )
        note = " ".join(notes)
    else:
        status = "ready"
        note = "Assignment counts are broker events."
        if calls:
            note = (
                f"{note} Called-away upside reference is strike-to-{reference_as_of:%b %d, %Y} "
                "close on assigned shares. It is opportunity context, not a realized loss, "
                "and ignores reinvestment."
            )
        else:
            note = f"{note} Upside reference does not apply because no calls were assigned."
    return AssignmentImpact(
        status=status,
        assigned_call_contracts=call_contracts,
        called_away_shares=called_away,
        assigned_put_contracts=put_contracts,
        acquired_shares=acquired,
        period_end_upside_reference=(sum(references, ZERO) if references else None),
        method_note=note,
        unknown_side_assignments=len(unknown),
        unknown_side_contracts=unknown_contracts,
        reference_as_of=reference_as_of,
        reference_age_days=reference_age_days,
        reference_quality=reference_quality,
    )


def _latest_closes(rows: Sequence[dict[str, Any]], end: date) -> dict[str, tuple[date, Decimal]]:
    latest: dict[str, tuple[date, Decimal]] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        day = row.get("trade_date")
        close = _optional_positive_decimal(row.get("close"))
        if not symbol or not isinstance(day, date) or day > end or close is None:
            continue
        previous = latest.get(symbol)
        if previous is None or day > previous[0]:
            latest[symbol] = (day, close)
    return latest


def _inside(value: date | None, start: date | None, end: date | None) -> bool:
    return value is not None and (start is None or value >= start) and (end is None or value <= end)


def _date(value: object) -> date | None:
    if isinstance(value, (date, datetime)):
        return ledger_market_date(value)
    return date.fromisoformat(str(value)) if value else None


def _decimal(value: object) -> Decimal:
    return ZERO if value is None else Decimal(str(value))


def _optional_positive_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    parsed = Decimal(str(value))
    return parsed if parsed > ZERO else None
