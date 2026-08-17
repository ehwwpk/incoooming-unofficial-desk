from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from schwab_dashboard.application.dashboard.anchors import option_contract_anchor
from schwab_dashboard.application.dashboard.covered_calls import (
    OpenCallClock,
    UnderlyingCallStats,
)
from schwab_dashboard.application.dashboard.models import (
    DashboardSnapshot,
    LiveOpenCallPosition,
    LiveUnderlyingPosition,
)
from schwab_dashboard.application.risk.models import UnderlyingRiskView
from schwab_dashboard.application.risk.projection import build_open_risk_summary

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class DeskOptionFocus:
    """One open option addressable from the compact Desk summary."""

    symbol: str
    option_type: str
    strike: Decimal
    strike_distance_per_share: Decimal
    strike_distance_percent: Decimal
    days_to_expiration: int
    expires_on: date
    anchor_id: str
    can_close_or_roll: bool


@dataclass(frozen=True, slots=True)
class DeskPositionRow:
    """One compact covered-call inventory row for the primary Desk."""

    underlying: UnderlyingCallStats
    nearest_call: DeskOptionFocus | None
    open_positions: int
    open_mark_profit_loss: Decimal
    alert_count: int
    live_underlying: LiveUnderlyingPosition | None
    risk: UnderlyingRiskView | None


@dataclass(frozen=True, slots=True)
class DeskOverview:
    """Decision-first projection for the covered-call seller's primary surface."""

    position_rows: Sequence[DeskPositionRow]
    open_positions: int
    open_contracts: int
    contract_capacity: int
    coverage_percent: Decimal
    open_mark_profit_loss: Decimal
    nearest_call: DeskOptionFocus | None
    next_expiring_option: DeskOptionFocus | None
    dividend_overlap_contracts: int
    alert_count: int
    underlying_count: int
    open_put_positions: int
    open_put_contracts: int
    open_call_positions: int
    open_call_contracts: int
    daily_theta: Decimal


def build_desk_overview(snapshot: DashboardSnapshot) -> DeskOverview:
    alert_counts = Counter(alert.symbol for alert in snapshot.alerts)
    rows: list[DeskPositionRow] = []
    all_calls: list[DeskOptionFocus] = []
    live_by_symbol = {
        item.symbol: item
        for item in (
            snapshot.live_position_book.underlyings
            if snapshot.live_position_book is not None
            else ()
        )
    }
    live_book = snapshot.live_position_book
    all_puts = [
        _live_option_focus(put) for put in (live_book.puts if live_book is not None else ())
    ]
    risk_summary = build_open_risk_summary(snapshot)
    risk_by_symbol = {
        item.symbol: item for item in (risk_summary.underlyings if risk_summary else ())
    }

    for underlying in snapshot.underlyings:
        calls = tuple(underlying.open_call_clocks)
        call_focuses = tuple(_call_focus(underlying.symbol, call) for call in calls)
        all_calls.extend(call_focuses)
        live_underlying = live_by_symbol.get(underlying.symbol)
        put_positions = tuple(live_underlying.puts) if live_underlying is not None else ()
        rows.append(
            DeskPositionRow(
                underlying=underlying,
                nearest_call=_nearest_call(call_focuses),
                open_positions=len(calls) + len(put_positions),
                open_mark_profit_loss=sum(
                    (call.open_profit_loss for call in calls),
                    ZERO,
                )
                + sum((put.open_profit_loss or ZERO for put in put_positions), ZERO),
                alert_count=alert_counts[underlying.symbol],
                live_underlying=live_underlying,
                risk=risk_by_symbol.get(underlying.symbol),
            )
        )

    if not snapshot.underlyings and live_book is not None:
        all_calls.extend(_live_option_focus(call) for call in live_book.calls)
        all_options = all_calls + all_puts
        return DeskOverview(
            position_rows=(),
            open_positions=live_book.open_call_positions + live_book.open_put_positions,
            open_contracts=live_book.open_call_contracts + live_book.open_put_contracts,
            contract_capacity=live_book.contract_capacity,
            coverage_percent=live_book.coverage_percent,
            open_mark_profit_loss=live_book.total_open_mark_profit_loss,
            nearest_call=_nearest_call(all_calls),
            next_expiring_option=min(
                (option for option in all_options if option.can_close_or_roll),
                key=lambda option: option.expires_on,
                default=None,
            ),
            dividend_overlap_contracts=0,
            alert_count=len(snapshot.alerts),
            underlying_count=len(live_book.underlyings),
            open_put_positions=live_book.open_put_positions,
            open_put_contracts=live_book.open_put_contracts,
            open_call_positions=live_book.open_call_positions,
            open_call_contracts=live_book.open_call_contracts,
            daily_theta=snapshot.risk.daily_theta,
        )

    open_put_positions = live_book.open_put_positions if live_book is not None else 0
    open_put_contracts = live_book.open_put_contracts if live_book is not None else 0
    all_options = all_calls + all_puts
    return DeskOverview(
        position_rows=tuple(rows),
        open_positions=len(all_calls) + open_put_positions,
        open_contracts=snapshot.covered_calls.active_contracts + open_put_contracts,
        contract_capacity=snapshot.covered_calls.contract_capacity,
        coverage_percent=snapshot.covered_calls.coverage_percent,
        open_mark_profit_loss=(
            snapshot.covered_calls.open_mark_profit_loss
            + sum(
                (put.open_profit_loss or ZERO for put in (live_book.puts if live_book else ())),
                ZERO,
            )
        ),
        nearest_call=_nearest_call(all_calls),
        next_expiring_option=min(
            (option for option in all_options if option.can_close_or_roll),
            key=lambda option: option.expires_on,
            default=None,
        ),
        dividend_overlap_contracts=sum(
            underlying.dividend_overlap_contracts for underlying in snapshot.underlyings
        ),
        alert_count=len(snapshot.alerts),
        underlying_count=len(rows),
        open_put_positions=open_put_positions,
        open_put_contracts=open_put_contracts,
        open_call_positions=len(all_calls),
        open_call_contracts=snapshot.covered_calls.active_contracts,
        daily_theta=snapshot.risk.daily_theta,
    )


def _call_focus(symbol: str, call: OpenCallClock) -> DeskOptionFocus:
    return DeskOptionFocus(
        symbol=symbol,
        option_type="CALL",
        strike=call.strike,
        strike_distance_per_share=call.strike_distance_per_share,
        strike_distance_percent=call.strike_distance_percent,
        days_to_expiration=call.days_to_expiration,
        expires_on=call.expires_on,
        anchor_id=option_contract_anchor(call.record_id),
        can_close_or_roll=call.can_close_or_roll,
    )


def _live_option_focus(option: LiveOpenCallPosition) -> DeskOptionFocus:
    return DeskOptionFocus(
        symbol=option.underlying_symbol,
        option_type=option.option_type,
        strike=option.strike,
        strike_distance_per_share=option.strike_distance_per_share or ZERO,
        strike_distance_percent=option.strike_distance_percent or ZERO,
        days_to_expiration=option.days_to_expiration,
        expires_on=option.expires_on,
        anchor_id=option_contract_anchor(option.option_symbol),
        can_close_or_roll=option.can_close_or_roll,
    )


def _nearest_call(calls: Sequence[DeskOptionFocus]) -> DeskOptionFocus | None:
    return min(
        (call for call in calls if call.can_close_or_roll),
        key=lambda call: call.strike_distance_percent,
        default=None,
    )
