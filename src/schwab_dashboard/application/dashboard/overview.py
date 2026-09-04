from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
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
from schwab_dashboard.application.dashboard.open_put_clocks import (
    OpenPutClock,
    build_open_put_clocks,
)
from schwab_dashboard.application.expiration import OptionExpirationAssessment
from schwab_dashboard.application.market_time import (
    market_date,
    quote_session_stamp,
    quote_session_state,
)
from schwab_dashboard.application.risk.models import UnderlyingRiskView
from schwab_dashboard.application.risk.projection import build_open_risk_summary
from schwab_dashboard.application.values import sum_if_complete

ZERO = Decimal("0")
NAME_OPTION_PRIORITY = 3
_MISSING_DISTANCE = Decimal("Infinity")


def open_contract_side_copy(call_contracts: int, put_contracts: int) -> str:
    """Lowercase sides that add to an open-contract total. Zero sides are omitted."""

    call_label = f"{call_contracts} call" + ("" if call_contracts == 1 else "s")
    put_label = f"{put_contracts} put" + ("" if put_contracts == 1 else "s")
    if call_contracts and put_contracts:
        return f"{call_label} · {put_label}"
    if put_contracts:
        return put_label
    return call_label


@dataclass(frozen=True, slots=True)
class DeskOptionFocus:
    """One open option addressable from the compact Desk summary."""

    symbol: str
    option_type: str
    strike: Decimal
    strike_distance_per_share: Decimal | None
    strike_distance_percent: Decimal | None
    days_to_expiration: int
    expires_on: date
    anchor_id: str
    can_close_or_roll: bool


@dataclass(frozen=True, slots=True)
class NameOptionSlot:
    """One short option in the name expansion, call or put."""

    side: str
    call: OpenCallClock | None = None
    put: OpenPutClock | None = None

    @property
    def expires_on(self) -> date:
        clock = self.call if self.call is not None else self.put
        assert clock is not None
        return clock.expires_on

    @property
    def strike(self) -> Decimal:
        clock = self.call if self.call is not None else self.put
        assert clock is not None
        return clock.strike

    @property
    def strike_distance_percent(self) -> Decimal | None:
        if self.call is not None:
            return self.call.strike_distance_percent
        assert self.put is not None
        return self.put.strike_distance_percent

    @property
    def can_close_or_roll(self) -> bool:
        clock = self.call if self.call is not None else self.put
        assert clock is not None
        return clock.can_close_or_roll

    @property
    def contracts(self) -> int:
        clock = self.call if self.call is not None else self.put
        assert clock is not None
        return clock.contracts

    @property
    def session_label(self) -> str:
        clock = self.call if self.call is not None else self.put
        assert clock is not None
        return clock.session_label

    @property
    def expiration_assessment(self) -> OptionExpirationAssessment | None:
        clock = self.call if self.call is not None else self.put
        assert clock is not None
        return clock.expiration_assessment

    @property
    def current_option_value(self) -> Decimal | None:
        clock = self.call if self.call is not None else self.put
        assert clock is not None
        return clock.current_option_value

    @property
    def open_profit_loss(self) -> Decimal | None:
        clock = self.call if self.call is not None else self.put
        assert clock is not None
        return clock.open_profit_loss

    @property
    def record_id(self) -> str:
        if self.call is not None:
            return self.call.record_id
        assert self.put is not None
        return self.put.option_symbol


@dataclass(frozen=True, slots=True)
class DeskPositionRow:
    """One compact covered-call inventory row for the primary Desk."""

    underlying: UnderlyingCallStats
    nearest_call: DeskOptionFocus | None
    open_positions: int
    open_call_contracts: int
    open_put_contracts: int
    open_mark_profit_loss: Decimal | None
    alert_count: int
    live_underlying: LiveUnderlyingPosition | None
    risk: UnderlyingRiskView | None
    put_clocks: tuple[OpenPutClock, ...] = ()
    evaluated_at: datetime | None = None
    pending_settlement_positions: int = 0
    pending_settlement_contracts: int = 0
    pending_last_mark_profit_loss: Decimal | None = ZERO
    broker_reported_call_contracts: int = 0
    broker_reported_put_contracts: int = 0

    @property
    def open_contracts(self) -> int:
        return self.open_call_contracts + self.open_put_contracts

    @property
    def broker_reported_contracts(self) -> int:
        return self.broker_reported_call_contracts + self.broker_reported_put_contracts

    @property
    def open_options(self) -> tuple[NameOptionSlot, ...]:
        return tuple(
            slot
            for slot in ordered_name_options(self.underlying.open_call_clocks, self.put_clocks)
            if slot.can_close_or_roll
        )

    @property
    def settling_options(self) -> tuple[NameOptionSlot, ...]:
        return tuple(
            slot
            for slot in ordered_name_options(self.underlying.open_call_clocks, self.put_clocks)
            if not slot.can_close_or_roll
        )

    @property
    def priority_options(self) -> tuple[NameOptionSlot, ...]:
        return self.open_options[:NAME_OPTION_PRIORITY]

    @property
    def overflow_options(self) -> tuple[NameOptionSlot, ...]:
        return self.open_options[NAME_OPTION_PRIORITY:]

    @property
    def overflow_call_count(self) -> int:
        return sum(1 for option in self.overflow_options if option.side == "call")

    @property
    def overflow_put_count(self) -> int:
        return sum(1 for option in self.overflow_options if option.side == "put")

    @property
    def priority_status_caption(self) -> str:
        if len(self.open_options) > NAME_OPTION_PRIORITY:
            return "NEAREST 3 BY EXPIRATION"
        return "BY EXPIRATION"

    @property
    def open_option_theta_per_day(self) -> Decimal | None:
        return sum_if_complete(
            (
                *(
                    clock.short_theta_per_day
                    for clock in self.underlying.open_call_clocks
                    if clock.can_close_or_roll
                ),
                *(
                    clock.short_theta_per_day
                    for clock in self.put_clocks
                    if clock.can_close_or_roll
                ),
            )
        )

    @property
    def open_option_value_now(self) -> Decimal | None:
        """Current marks of every open short on this name, calls and puts.

        None when this name has no option clocks, so the tape can show a dash
        instead of a fake $0.00 overlay. Zero marks on live shorts stay zero.
        """

        actionable_calls = tuple(
            clock for clock in self.underlying.open_call_clocks if clock.can_close_or_roll
        )
        actionable_puts = tuple(clock for clock in self.put_clocks if clock.can_close_or_roll)
        if not actionable_calls and not actionable_puts:
            return None
        return sum_if_complete(
            (
                *(clock.current_option_value for clock in actionable_calls),
                *(put.current_option_value for put in actionable_puts),
            )
        )

    @property
    def open_option_entry_credit(self) -> Decimal | None:
        return sum_if_complete(
            (
                *(
                    clock.entry_credit
                    for clock in self.underlying.open_call_clocks
                    if clock.can_close_or_roll
                ),
                *(clock.entry_credit for clock in self.put_clocks if clock.can_close_or_roll),
            )
        )

    @property
    def open_option_mark_is_prior_session(self) -> bool:
        return self.open_option_mark_stamp is not None or any(
            self._clock_is_prior(clock) for clock in self._mark_clocks
        )

    @property
    def open_option_mark_stamp(self) -> str | None:
        evaluated = self._mark_evaluated_at
        stamps: list[tuple[datetime, str]] = []
        for clock in self._mark_clocks:
            observed = getattr(clock, "quote_observed_at", None)
            if observed is None or evaluated is None:
                continue
            if quote_session_state(observed, evaluated_at=evaluated).is_prior_session:
                stamps.append((observed, quote_session_stamp(observed, evaluated_at=evaluated)))
        if not stamps:
            return None
        return min(stamps, key=lambda item: item[0])[1]

    @property
    def _mark_evaluated_at(self) -> datetime | None:
        if self.evaluated_at is not None:
            return self.evaluated_at
        if self.live_underlying is not None:
            return self.live_underlying.quote_evaluated_at
        return None

    @property
    def _mark_clocks(self) -> tuple[OpenCallClock | OpenPutClock, ...]:
        clocks: list[OpenCallClock | OpenPutClock] = []
        clocks.extend(
            clock for clock in self.underlying.open_call_clocks if clock.can_close_or_roll
        )
        clocks.extend(clock for clock in self.put_clocks if clock.can_close_or_roll)
        return tuple(clocks)

    def _clock_is_prior(self, clock: OpenCallClock | OpenPutClock) -> bool:
        evaluated = self._mark_evaluated_at
        if evaluated is None:
            return False
        observed_at = clock.quote_observed_at
        if observed_at is not None:
            return quote_session_state(observed_at, evaluated_at=evaluated).is_prior_session
        observed_on = clock.quote_observed_on
        if observed_on is None:
            return False
        return observed_on < market_date(evaluated)

    @property
    def average_open_option_iv_percent(self) -> Decimal | None:
        samples = [
            *(
                (clock.implied_volatility_percent, clock.contracts)
                for clock in self.underlying.open_call_clocks
                if clock.can_close_or_roll and clock.implied_volatility_percent is not None
            ),
            *(
                (clock.implied_volatility_percent, clock.contracts)
                for clock in self.put_clocks
                if clock.can_close_or_roll and clock.implied_volatility_percent is not None
            ),
        ]
        weight = sum(contracts for _, contracts in samples)
        if not weight:
            return self.underlying.average_open_call_iv_percent
        return sum(
            (value * Decimal(contracts) for value, contracts in samples),
            ZERO,
        ) / Decimal(weight)

    @property
    def open_iv_caption(self) -> str:
        """Call-only copy when puts exist but none of them reported IV."""

        actionable_puts = tuple(clock for clock in self.put_clocks if clock.can_close_or_roll)
        put_iv = any(clock.implied_volatility_percent is not None for clock in actionable_puts)
        if actionable_puts and not put_iv:
            return "AVG OPEN CALL IV"
        return "AVG OPEN IV"


@dataclass(frozen=True, slots=True)
class DeskOverview:
    """Decision-first projection for the covered-call seller's primary surface."""

    position_rows: Sequence[DeskPositionRow]
    open_positions: int
    open_contracts: int
    contract_capacity: int
    coverage_percent: Decimal
    open_mark_profit_loss: Decimal | None
    nearest_call: DeskOptionFocus | None
    next_expiring_option: DeskOptionFocus | None
    dividend_overlap_contracts: int
    alert_count: int
    underlying_count: int
    open_put_positions: int
    open_put_contracts: int
    open_call_positions: int
    open_call_contracts: int
    daily_theta: Decimal | None
    broker_reported_positions: int = 0
    broker_reported_contracts: int = 0
    pending_settlement_positions: int = 0
    pending_settlement_contracts: int = 0
    pending_last_mark_profit_loss: Decimal | None = ZERO
    broker_reported_call_contracts: int = 0
    broker_reported_put_contracts: int = 0


def ordered_name_options(
    calls: Sequence[OpenCallClock],
    puts: Sequence[OpenPutClock],
) -> tuple[NameOptionSlot, ...]:
    """Nearest expirations first; proximity; call before put; put strikes high to low."""

    slots = (
        *(NameOptionSlot(side="call", call=clock) for clock in calls),
        *(NameOptionSlot(side="put", put=clock) for clock in puts),
    )
    return tuple(sorted(slots, key=name_option_sort_key))


def name_option_sort_key(slot: NameOptionSlot) -> tuple[object, ...]:
    percent = slot.strike_distance_percent
    abs_distance = abs(percent) if percent is not None else _MISSING_DISTANCE
    side_rank = 0 if slot.side == "call" else 1
    strike_order = slot.strike if slot.side == "call" else -slot.strike
    return (slot.expires_on, abs_distance, side_rank, strike_order)


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
        actionable_calls = tuple(call for call in calls if call.can_close_or_roll)
        settling_calls = tuple(call for call in calls if not call.can_close_or_roll)
        call_focuses = tuple(_call_focus(underlying.symbol, call) for call in actionable_calls)
        all_calls.extend(call_focuses)
        live_underlying = live_by_symbol.get(underlying.symbol)
        put_positions = tuple(live_underlying.puts) if live_underlying is not None else ()
        actionable_puts = tuple(put for put in put_positions if put.can_close_or_roll)
        settling_puts = tuple(put for put in put_positions if not put.can_close_or_roll)
        open_call_contracts = sum(call.contracts for call in actionable_calls)
        open_put_contracts = sum(put.contracts for put in actionable_puts)
        rows.append(
            DeskPositionRow(
                underlying=underlying,
                nearest_call=_nearest_call(call_focuses),
                open_positions=len(actionable_calls) + len(actionable_puts),
                open_call_contracts=open_call_contracts,
                open_put_contracts=open_put_contracts,
                open_mark_profit_loss=sum_if_complete(
                    (
                        *(call.open_profit_loss for call in actionable_calls),
                        *(put.open_profit_loss for put in actionable_puts),
                    )
                ),
                alert_count=alert_counts[underlying.symbol],
                live_underlying=live_underlying,
                risk=risk_by_symbol.get(underlying.symbol),
                put_clocks=build_open_put_clocks(
                    put_positions,
                    campaigns=snapshot.campaigns,
                ),
                evaluated_at=snapshot.as_of,
                pending_settlement_positions=len(settling_calls) + len(settling_puts),
                pending_settlement_contracts=sum(call.contracts for call in settling_calls)
                + sum(put.contracts for put in settling_puts),
                pending_last_mark_profit_loss=sum_if_complete(
                    (
                        *(call.open_profit_loss for call in settling_calls),
                        *(put.open_profit_loss for put in settling_puts),
                    )
                ),
                broker_reported_call_contracts=sum(call.contracts for call in calls),
                broker_reported_put_contracts=sum(put.contracts for put in put_positions),
            )
        )

    if not snapshot.underlyings and live_book is not None:
        all_calls.extend(_live_option_focus(call) for call in live_book.calls)
        all_options = all_calls + all_puts
        return DeskOverview(
            position_rows=(),
            open_positions=len(live_book.actionable_options),
            open_contracts=live_book.actionable_contracts,
            contract_capacity=live_book.contract_capacity,
            coverage_percent=live_book.coverage_percent,
            open_mark_profit_loss=live_book.actionable_open_mark_profit_loss,
            nearest_call=_nearest_call(all_calls),
            next_expiring_option=min(
                (option for option in all_options if option.can_close_or_roll),
                key=lambda option: option.expires_on,
                default=None,
            ),
            dividend_overlap_contracts=0,
            alert_count=len(snapshot.alerts),
            underlying_count=len(live_book.underlyings),
            open_put_positions=sum(put.can_close_or_roll for put in live_book.puts),
            open_put_contracts=sum(
                put.contracts for put in live_book.puts if put.can_close_or_roll
            ),
            open_call_positions=sum(call.can_close_or_roll for call in live_book.calls),
            open_call_contracts=sum(
                call.contracts for call in live_book.calls if call.can_close_or_roll
            ),
            daily_theta=sum_if_complete(
                option.price_time_read.theta_per_day for option in live_book.actionable_options
            ),
            broker_reported_positions=len(live_book.options),
            broker_reported_contracts=sum(option.contracts for option in live_book.options),
            pending_settlement_positions=len(live_book.settling_options),
            pending_settlement_contracts=live_book.settling_contracts,
            pending_last_mark_profit_loss=live_book.settling_last_mark_profit_loss,
            broker_reported_call_contracts=sum(call.contracts for call in live_book.calls),
            broker_reported_put_contracts=sum(put.contracts for put in live_book.puts),
        )

    actionable_puts = tuple(
        put for put in (live_book.puts if live_book is not None else ()) if put.can_close_or_roll
    )
    open_put_positions = len(actionable_puts)
    open_put_contracts = sum(put.contracts for put in actionable_puts)
    actionable_call_clocks = tuple(
        clock
        for underlying in snapshot.underlyings
        for clock in underlying.open_call_clocks
        if clock.can_close_or_roll
    )
    all_options = all_calls + all_puts
    return DeskOverview(
        position_rows=tuple(rows),
        open_positions=len(all_calls) + open_put_positions,
        open_contracts=sum(clock.contracts for clock in actionable_call_clocks)
        + open_put_contracts,
        contract_capacity=snapshot.covered_calls.contract_capacity,
        coverage_percent=snapshot.covered_calls.coverage_percent,
        open_mark_profit_loss=sum_if_complete(row.open_mark_profit_loss for row in rows),
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
        open_call_contracts=sum(clock.contracts for clock in actionable_call_clocks),
        daily_theta=sum_if_complete(row.open_option_theta_per_day for row in rows),
        broker_reported_positions=(len(live_book.options) if live_book is not None else 0),
        broker_reported_contracts=(
            sum(option.contracts for option in live_book.options) if live_book is not None else 0
        ),
        pending_settlement_positions=(
            len(live_book.settling_options) if live_book is not None else 0
        ),
        pending_settlement_contracts=(live_book.settling_contracts if live_book is not None else 0),
        pending_last_mark_profit_loss=(
            live_book.settling_last_mark_profit_loss if live_book is not None else ZERO
        ),
        broker_reported_call_contracts=(
            sum(call.contracts for call in live_book.calls)
            if live_book is not None
            else sum(
                clock.contracts
                for underlying in snapshot.underlyings
                for clock in underlying.open_call_clocks
            )
        ),
        broker_reported_put_contracts=(
            sum(put.contracts for put in live_book.puts) if live_book is not None else 0
        ),
    )


def _open_contract_counts(
    underlying: UnderlyingCallStats,
    live_underlying: LiveUnderlyingPosition | None,
) -> tuple[int, int]:
    return (
        underlying.active_contracts,
        live_underlying.open_put_contracts if live_underlying is not None else 0,
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
        strike_distance_per_share=option.strike_distance_per_share,
        strike_distance_percent=option.strike_distance_percent,
        days_to_expiration=option.days_to_expiration,
        expires_on=option.expires_on,
        anchor_id=option_contract_anchor(option.option_symbol),
        can_close_or_roll=option.can_close_or_roll,
    )


def _nearest_call(calls: Sequence[DeskOptionFocus]) -> DeskOptionFocus | None:
    return min(
        (call for call in calls if call.can_close_or_roll),
        key=lambda call: (
            call.strike_distance_percent is None,
            abs(call.strike_distance_percent)
            if call.strike_distance_percent is not None
            else _MISSING_DISTANCE,
            call.expires_on,
        ),
        default=None,
    )
