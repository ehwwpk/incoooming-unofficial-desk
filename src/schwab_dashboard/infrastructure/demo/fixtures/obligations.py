from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from schwab_dashboard.application.dashboard.covered_calls import (
    OpenCallClock,
    UnderlyingCallStats,
)
from schwab_dashboard.application.dashboard.performance import ExpirationBucket
from schwab_dashboard.application.values import sum_if_complete

D = Decimal
ZERO = D("0")
TENTH = D("0.1")


def build_expiration_calendar(
    underlyings: Sequence[UnderlyingCallStats], as_of: date
) -> tuple[ExpirationBucket, ...]:
    grouped: dict[date, list[tuple[UnderlyingCallStats, OpenCallClock]]] = defaultdict(list)
    for underlying in underlyings:
        for clock in underlying.open_call_clocks:
            grouped[clock.expires_on].append((underlying, clock))

    return tuple(_bucket(expires_on, grouped[expires_on], as_of) for expires_on in sorted(grouped))


def _bucket(
    expires_on: date,
    rows: Sequence[tuple[UnderlyingCallStats, OpenCallClock]],
    as_of: date,
) -> ExpirationBucket:
    contracts = sum(clock.contracts for _, clock in rows)
    events = {
        f"{underlying.symbol} ex-dividend {underlying.next_ex_dividend_date:%b %d}"
        for underlying, _ in rows
        if underlying.next_ex_dividend_date is not None
        and underlying.next_ex_dividend_date <= expires_on
    }
    opening_credit = sum_if_complete(clock.entry_credit for _, clock in rows)
    estimated_close_value = sum_if_complete(clock.current_option_value for _, clock in rows)
    known_buffers = tuple(
        clock.strike_distance_percent
        for _, clock in rows
        if clock.strike_distance_percent is not None
    )
    assert opening_credit is not None
    assert estimated_close_value is not None
    assert known_buffers
    return ExpirationBucket(
        expires_on=expires_on,
        days_to_expiration=max(0, (expires_on - as_of).days),
        positions=len(rows),
        contracts=contracts,
        committed_shares=sum_if_complete(clock.obligated_shares for _, clock in rows),
        opening_credit=opening_credit,
        estimated_close_value=estimated_close_value,
        nearest_strike_buffer_percent=min(known_buffers).quantize(TENTH),
        event_labels=tuple(sorted(events)),
    )
