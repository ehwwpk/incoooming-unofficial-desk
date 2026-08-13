from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from schwab_dashboard.application.dashboard.covered_calls import (
    OpenCallClock,
    UnderlyingCallStats,
)
from schwab_dashboard.application.dashboard.models import LiveOpenOptionPosition
from schwab_dashboard.application.dashboard.performance import ExpirationBucket

ZERO = Decimal("0")


def build_expiration_calendar(
    underlyings: Sequence[UnderlyingCallStats],
    as_of: date,
    put_positions: Sequence[LiveOpenOptionPosition] = (),
) -> tuple[ExpirationBucket, ...]:
    grouped: dict[date, list[tuple[UnderlyingCallStats, OpenCallClock]]] = defaultdict(list)
    grouped_puts: dict[date, list[LiveOpenOptionPosition]] = defaultdict(list)
    for underlying in underlyings:
        for clock in underlying.open_call_clocks:
            grouped[clock.expires_on].append((underlying, clock))
    for put in put_positions:
        grouped_puts[put.expires_on].append(put)
    return tuple(
        _bucket(
            expires_on,
            grouped[expires_on],
            grouped_puts[expires_on],
            as_of,
        )
        for expires_on in sorted(set(grouped) | set(grouped_puts))
    )


def _bucket(
    expires_on: date,
    rows: Sequence[tuple[UnderlyingCallStats, OpenCallClock]],
    puts: Sequence[LiveOpenOptionPosition],
    as_of: date,
) -> ExpirationBucket:
    call_contracts = sum(clock.contracts for _, clock in rows)
    put_contracts = sum(put.contracts for put in puts)
    contracts = call_contracts + put_contracts
    events = {
        f"{underlying.symbol} ex-dividend {underlying.next_ex_dividend_date:%b %d}"
        for underlying, _ in rows
        if underlying.next_ex_dividend_date is not None
        and underlying.next_ex_dividend_date <= expires_on
    }
    return ExpirationBucket(
        expires_on=expires_on,
        days_to_expiration=max(0, (expires_on - as_of).days),
        positions=len(rows) + len(puts),
        contracts=contracts,
        committed_shares=contracts * 100,
        opening_credit=sum((clock.entry_credit for _, clock in rows), ZERO)
        + sum(
            (
                (put.entry_credit_per_share or ZERO) * Decimal("100") * Decimal(put.contracts)
                for put in puts
            ),
            ZERO,
        ),
        estimated_close_value=sum((clock.current_option_value for _, clock in rows), ZERO)
        + sum(
            (
                abs(put.market_value)
                if put.market_value is not None
                else (put.estimated_mark_per_share or ZERO)
                * Decimal("100")
                * Decimal(put.contracts)
                for put in puts
            ),
            ZERO,
        ),
        nearest_strike_buffer_percent=min(
            (
                *(clock.strike_distance_percent for _, clock in rows),
                *(put.strike_distance_percent or ZERO for put in puts),
            ),
            key=abs,
            default=ZERO,
        ),
        event_labels=tuple(sorted(events)),
        call_contracts=call_contracts,
        put_contracts=put_contracts,
    )
