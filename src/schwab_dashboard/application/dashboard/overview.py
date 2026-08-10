from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from schwab_dashboard.application.dashboard.covered_calls import (
    OpenCallClock,
    UnderlyingCallStats,
)
from schwab_dashboard.application.dashboard.models import DashboardSnapshot

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class DeskCallFocus:
    """The open call with the least remaining strike cushion."""

    symbol: str
    strike: Decimal
    strike_distance_per_share: Decimal
    strike_distance_percent: Decimal
    days_to_expiration: int
    expires_on: date


@dataclass(frozen=True, slots=True)
class DeskPositionRow:
    """One compact covered-call inventory row for the primary Desk."""

    underlying: UnderlyingCallStats
    nearest_call: DeskCallFocus | None
    open_positions: int
    open_mark_profit_loss: Decimal
    alert_count: int


@dataclass(frozen=True, slots=True)
class DeskOverview:
    """Decision-first projection for the covered-call seller's primary surface."""

    position_rows: Sequence[DeskPositionRow]
    open_positions: int
    open_contracts: int
    contract_capacity: int
    coverage_percent: Decimal
    open_mark_profit_loss: Decimal
    nearest_call: DeskCallFocus | None
    next_expiring_call: DeskCallFocus | None
    dividend_overlap_contracts: int
    alert_count: int


def build_desk_overview(snapshot: DashboardSnapshot) -> DeskOverview:
    alert_counts = Counter(alert.symbol for alert in snapshot.alerts)
    rows: list[DeskPositionRow] = []
    all_calls: list[DeskCallFocus] = []

    for underlying in snapshot.underlyings:
        calls = tuple(underlying.open_call_clocks)
        call_focuses = tuple(_call_focus(underlying.symbol, call) for call in calls)
        all_calls.extend(call_focuses)
        rows.append(
            DeskPositionRow(
                underlying=underlying,
                nearest_call=_nearest_call(call_focuses),
                open_positions=len(calls),
                open_mark_profit_loss=sum(
                    (call.open_profit_loss for call in calls),
                    ZERO,
                ),
                alert_count=alert_counts[underlying.symbol],
            )
        )

    return DeskOverview(
        position_rows=tuple(rows),
        open_positions=len(all_calls),
        open_contracts=snapshot.covered_calls.active_contracts,
        contract_capacity=snapshot.covered_calls.contract_capacity,
        coverage_percent=snapshot.covered_calls.coverage_percent,
        open_mark_profit_loss=snapshot.covered_calls.open_mark_profit_loss,
        nearest_call=_nearest_call(all_calls),
        next_expiring_call=min(all_calls, key=lambda call: call.expires_on, default=None),
        dividend_overlap_contracts=sum(
            underlying.dividend_overlap_contracts for underlying in snapshot.underlyings
        ),
        alert_count=len(snapshot.alerts),
    )


def _call_focus(symbol: str, call: OpenCallClock) -> DeskCallFocus:
    return DeskCallFocus(
        symbol=symbol,
        strike=call.strike,
        strike_distance_per_share=call.strike_distance_per_share,
        strike_distance_percent=call.strike_distance_percent,
        days_to_expiration=call.days_to_expiration,
        expires_on=call.expires_on,
    )


def _nearest_call(calls: Sequence[DeskCallFocus]) -> DeskCallFocus | None:
    return min(calls, key=lambda call: call.strike_distance_percent, default=None)
