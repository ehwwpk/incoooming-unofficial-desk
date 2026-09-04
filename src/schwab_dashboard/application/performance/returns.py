from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from schwab_dashboard.application.market_time import (
    STANDARD_OPTION_LAST_TRADE,
    market_date,
    market_datetime,
)
from schwab_dashboard.application.performance.flows import (
    external_flow_between_instants,
    has_external_flow_between_instants,
    has_unexplained_cash_between_instants,
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
    cohorts: dict[date, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    legacy: dict[date, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in balance_history:
        observed_at = row.get("observed_at")
        if observed_at is None:
            continue
        # Snapshots are persisted as normalized UTC instants.  A Friday-evening
        # sync is already Saturday in UTC, but it still belongs to Friday's U.S.
        # market session.  Grouping on ``datetime.date()`` double-counted that
        # same broker opening balance as a second return day.
        day = market_date(observed_at)
        run_id = str(row.get("sync_run_id") or "")
        if run_id:
            cohorts[day][run_id].append(row)
            continue
        if calendar is not None and not calendar.is_session(day):
            continue
        account = str(row.get("account_id") or row.get("account_mask") or "ACCOUNT")
        existing = legacy[day].get(account)
        if existing is None or existing["observed_at"] <= observed_at:
            legacy[day][account] = row

    grouped: dict[date, dict[str, dict[str, Any]]] = dict(legacy)
    for day, runs in cohorts.items():
        if calendar is not None and not calendar.is_session(day):
            continue
        latest_rows = max(
            runs.values(),
            key=lambda rows: max(row["observed_at"] for row in rows),
        )
        grouped[day] = {_account_key(row): row for row in latest_rows}
    unitization_cohorts = tuple(
        cohort
        for runs in cohorts.values()
        for rows in runs.values()
        if (cohort := _observed_cohort(rows)) is not None
    )

    points: list[ReturnPoint] = []
    cumulative_factor = Decimal("1")
    previous_value: Decimal | None = None
    previous_day: date | None = None
    previous_accounts: frozenset[str] | None = None
    previous_value_quality: str | None = None
    previous_phase: str | None = None
    previous_at: datetime | None = None
    chain_complete = True
    for day, accounts in sorted(grouped.items()):
        rows = tuple(accounts.values())
        current_values = [_optional_decimal(row.get("liquidation_value")) for row in rows]
        if not current_values or any(value is None for value in current_values):
            continue
        value = sum((item for item in current_values if item is not None), ZERO)
        valuation_at = max(_timestamp(row.get("observed_at")) for row in rows)
        current_accounts = frozenset(accounts)
        flow_accounts = (
            current_accounts if previous_accounts is None else current_accounts | previous_accounts
        )
        # The first stored value is the comparison anchor. Counting the broker's
        # opening balance on that first day would make the managed series begin
        # before the frozen-share and market series, overstating management's
        # difference by one unmatched session.
        flow = (
            ZERO
            if previous_at is None
            else external_flow_between_instants(
                cash_movements,
                after=previous_at,
                through=valuation_at,
                accounts=flow_accounts,
            )
        )
        has_owner_flow = previous_at is not None and has_external_flow_between_instants(
            cash_movements,
            after=previous_at,
            through=valuation_at,
            accounts=flow_accounts,
        )
        has_unexplained_cash = previous_at is not None and has_unexplained_cash_between_instants(
            cash_movements,
            after=previous_at,
            through=valuation_at,
            accounts=flow_accounts,
        )
        daily_return: Decimal | None = None
        interval_return: Decimal | None = None
        return_quality = "unresolved"
        quality = "observed_anchor"
        value_quality = _value_quality(rows)
        valuation_phase = _valuation_phase(rows)
        session_span = calendar.session_span(previous_day, day) if calendar and previous_day else 0
        # Chain against the previous stored valuation rather than the broker's
        # stated opening balance. The two disagree whenever overnight
        # processing lands between the last sync and the next session, and
        # measuring from the broker's opening silently discards the P/L in that
        # seam instead of attributing it to anyone.
        same_account_coverage = previous_accounts is None or current_accounts == previous_accounts
        if previous_value is not None and not same_account_coverage:
            quality = "account_coverage_changed"
            chain_complete = False
        elif previous_value is not None and has_unexplained_cash:
            quality = "unexplained_cash_movement"
            return_quality = "unresolved"
            chain_complete = False
        elif previous_value == ZERO:
            quality = "zero_prior_value"
            chain_complete = False
        elif previous_value is not None and previous_value != ZERO:
            assert previous_at is not None
            interval_return = _unitized_interval_return(
                previous_at=previous_at,
                previous_value=previous_value,
                valuation_at=valuation_at,
                value=value,
                accounts=current_accounts,
                cash_movements=cash_movements,
                cohorts=unitization_cohorts if has_owner_flow else (),
            )
            if interval_return is None:
                quality = "unresolved_valuation_cohort"
                return_quality = "unresolved"
                chain_complete = False
            else:
                cumulative_factor *= Decimal("1") + interval_return / HUNDRED
                if calendar is None:
                    session_span = 1
                if session_span == 1:
                    return_quality = _return_quality(
                        previous_value_quality,
                        value_quality,
                        previous_phase,
                        valuation_phase,
                    )
                    if has_owner_flow and return_quality != "unresolved":
                        # Intraday unitization narrows the timing gap but the
                        # broker snapshot need not coincide exactly with cash.
                        return_quality = "estimated"
                    daily_return = interval_return
                    quality = (
                        "linked"
                        if return_quality == "observed" and chain_complete
                        else "linked_after_incomplete_history"
                        if return_quality == "observed"
                        else return_quality
                    )
                else:
                    return_quality = "multi_session"
                    quality = "multi_session"
        else:
            return_quality = "unresolved"
        if previous_value is None:
            return_quality = "unresolved"
        points.append(
            ReturnPoint(
                date=day,
                value=value,
                external_flow=flow,
                daily_return_percent=daily_return,
                interval_return_percent=interval_return,
                cumulative_return_percent=(
                    (cumulative_factor - Decimal("1")) * HUNDRED
                    if interval_return is not None and chain_complete
                    else None
                ),
                quality=quality,
                value_quality=value_quality,
                return_quality=return_quality,
                valuation_phase=valuation_phase,
                previous_date=previous_day,
                session_span=session_span,
                price_coverage_percent=_aggregate_price_coverage(rows),
                estimated_symbols=tuple(
                    sorted(
                        {
                            str(symbol)
                            for row in rows
                            for symbol in (row.get("estimated_symbols") or ())
                        }
                    )
                ),
                reconciliation_adjustment=sum(
                    (
                        _optional_decimal(row.get("reconciliation_adjustment")) or ZERO
                        for row in rows
                    ),
                    ZERO,
                ),
                anchor_start=_common_date(rows, "anchor_start"),
                anchor_end=_common_date(rows, "anchor_end"),
                valuation_subtype=_common_text(rows, "valuation_subtype"),
                raw_reconstructed_value=_aggregate_raw_value(rows),
            )
        )
        previous_value = value
        previous_day = day
        previous_accounts = current_accounts
        previous_value_quality = value_quality
        previous_phase = valuation_phase
        previous_at = valuation_at
    return tuple(points)


def _account_key(row: dict[str, Any]) -> str:
    return str(row.get("account_id") or row.get("account_mask") or "ACCOUNT")


def _observed_cohort(
    rows: Sequence[dict[str, Any]],
) -> tuple[datetime, Decimal, frozenset[str]] | None:
    """Aggregate one atomic broker sync when every account has a usable value."""

    if not rows or any(row.get("synthetic") for row in rows):
        return None
    if any(str(row.get("valuation_quality") or "observed") != "observed" for row in rows):
        return None
    timestamps = {_timestamp(row.get("observed_at")) for row in rows}
    if len(timestamps) != 1:
        return None
    accounts = [_account_key(row) for row in rows]
    if len(set(accounts)) != len(accounts):
        return None
    values = [_optional_decimal(row.get("liquidation_value")) for row in rows]
    if any(value is None for value in values):
        return None
    return (
        next(iter(timestamps)),
        sum((value for value in values if value is not None), ZERO),
        frozenset(accounts),
    )


def _unitized_interval_return(
    *,
    previous_at: datetime,
    previous_value: Decimal,
    valuation_at: datetime,
    value: Decimal,
    accounts: frozenset[str],
    cash_movements: Sequence[dict[str, Any]],
    cohorts: Sequence[tuple[datetime, Decimal, frozenset[str]]],
) -> Decimal | None:
    """Chain complete intraday valuations around owner cash events.

    Intermediate snapshots without a flow telescope away.  Around a flow they
    move the capital base from the prior close toward the broker's nearest
    observed valuation, materially reducing the endpoint-flow timing bias.
    """

    values_at: dict[datetime, set[Decimal]] = defaultdict(set)
    for observed_at, cohort_value, cohort_accounts in cohorts:
        if previous_at < observed_at < valuation_at and cohort_accounts == accounts:
            values_at[observed_at].add(cohort_value)
    if any(len(values) != 1 for values in values_at.values()):
        return None
    if not values_at:
        flow = external_flow_between_instants(
            cash_movements,
            after=previous_at,
            through=valuation_at,
            accounts=accounts,
        )
        return (value - previous_value - flow) / previous_value * HUNDRED

    checkpoints = [
        (observed_at, next(iter(values))) for observed_at, values in sorted(values_at.items())
    ]
    checkpoints.append((valuation_at, value))
    factor = Decimal("1")
    start_at = previous_at
    start_value = previous_value
    for end_at, end_value in checkpoints:
        if start_value == ZERO:
            return None
        flow = external_flow_between_instants(
            cash_movements,
            after=start_at,
            through=end_at,
            accounts=accounts,
        )
        factor *= Decimal("1") + (end_value - start_value - flow) / start_value
        start_at = end_at
        start_value = end_value
    return (factor - Decimal("1")) * HUNDRED


def _value_quality(rows: Sequence[dict[str, Any]]) -> str:
    qualities = {str(row.get("valuation_quality") or "observed") for row in rows}
    if "unresolved" in qualities:
        return "unresolved"
    if "estimated" in qualities:
        return "estimated"
    if "derived" in qualities:
        return "derived"
    return "observed"


def _valuation_phase(rows: Sequence[dict[str, Any]]) -> str:
    if any(row.get("synthetic") for row in rows):
        return "close"
    observed = [row.get("observed_at") for row in rows]
    if not observed or any(not isinstance(value, datetime) for value in observed):
        return "unknown"
    timestamps = [value for value in observed if isinstance(value, datetime)]
    return (
        "close"
        if all(
            market_datetime(value).timetz().replace(tzinfo=None) >= STANDARD_OPTION_LAST_TRADE
            for value in timestamps
        )
        else "intraday"
    )


def _return_quality(
    previous_quality: str | None,
    current_quality: str,
    previous_phase: str | None,
    current_phase: str,
) -> str:
    if previous_quality == "unresolved" or current_quality == "unresolved":
        return "unresolved"
    if previous_phase != "close" or current_phase != "close":
        return "provisional"
    if previous_quality == "estimated" or current_quality == "estimated":
        return "estimated"
    if previous_quality == "derived" or current_quality == "derived":
        return "derived"
    return "observed"


def _aggregate_price_coverage(rows: Sequence[dict[str, Any]]) -> Decimal | None:
    synthetic = [row for row in rows if row.get("synthetic")]
    if not synthetic:
        return None
    values = [_optional_decimal(row.get("price_coverage_percent")) for row in synthetic]
    if any(value is None for value in values):
        return None
    return min(value for value in values if value is not None)


def _aggregate_raw_value(rows: Sequence[dict[str, Any]]) -> Decimal | None:
    if not any(row.get("synthetic") for row in rows):
        return None
    values = [
        _optional_decimal(
            row.get("raw_reconstructed_value")
            if row.get("synthetic")
            else row.get("liquidation_value")
        )
        for row in rows
    ]
    if any(value is None for value in values):
        return None
    return sum((value for value in values if value is not None), ZERO)


def _common_date(rows: Sequence[dict[str, Any]], field: str) -> date | None:
    values = {row.get(field) for row in rows if isinstance(row.get(field), date)}
    return next(iter(values)) if len(values) == 1 else None


def _common_text(rows: Sequence[dict[str, Any]], field: str) -> str | None:
    values = {str(row.get(field)) for row in rows if row.get(field)}
    return next(iter(values)) if len(values) == 1 else "mixed" if values else None


def _optional_decimal(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time(), tzinfo=UTC)
    return datetime.min.replace(tzinfo=UTC)
