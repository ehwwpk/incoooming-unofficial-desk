from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal

from schwab_dashboard.application.dashboard.covered_calls import (
    OpenCallClock,
    UnderlyingCallStats,
)
from schwab_dashboard.application.dashboard.models import (
    DashboardSnapshot,
    LiveOpenOptionPosition,
)
from schwab_dashboard.application.market_time import OptionSessionState
from schwab_dashboard.application.policy.evaluate import evaluate_policy_fit
from schwab_dashboard.application.policy.models import CallPolicy
from schwab_dashboard.application.risk.models import OpenRiskSummary
from schwab_dashboard.application.risk.price_time import PriceTimeRead, build_price_time_read
from schwab_dashboard.application.risk.projection import build_open_risk_summary
from schwab_dashboard.application.volatility.calculate import analyze_volatility_history
from schwab_dashboard.application.volatility.models import DailyVolatilityObservation


@dataclass(frozen=True, slots=True)
class OpenCallRow:
    record_id: str
    campaign_id: str
    symbol: str
    contracts: int
    strike: Decimal
    sold_on: date
    expires_on: date
    original_days_to_expiration: int
    days_to_expiration: int
    obligated_shares: int
    strike_distance_per_share: Decimal
    strike_distance_percent: Decimal
    entry_credit: Decimal
    current_liability: Decimal
    open_profit_loss: Decimal
    theta_estimate_per_day: Decimal
    elapsed_time_percent: Decimal
    time_remaining_percent: Decimal
    credit_capture_percent: Decimal
    option_value_vs_credit_percent: Decimal
    option_value_track_percent: Decimal
    option_value_overrun_percent: Decimal
    decay_stage: str
    policy_label: str
    intent_label: str
    policy_fit_summary: str
    policy_fits: bool
    entry_credit_per_share: Decimal
    bid_per_share: Decimal
    mark_per_share: Decimal
    close_ask_per_share: Decimal
    spread_per_share: Decimal
    quote_status: str
    quote_observed_on: date | None
    implied_volatility_percent: Decimal | None
    delta: Decimal | None
    gamma: Decimal | None
    theta_per_share: Decimal | None
    vega: Decimal | None
    position_delta_share_equivalent: Decimal | None
    position_gamma_delta_change_per_dollar: Decimal | None
    position_vega_per_volatility_point: Decimal | None
    price_time_read: PriceTimeRead
    volume: int | None
    open_interest: int | None
    intrinsic_value: Decimal
    remaining_extrinsic_value: Decimal
    next_event_label: str
    session_state: OptionSessionState
    session_label: str
    can_close_or_roll: bool


@dataclass(frozen=True, slots=True)
class OpenCallGroup:
    symbol: str
    rows: tuple[OpenCallRow, ...]
    position_count: int
    contract_count: int
    nearest_buffer_percent: Decimal
    next_expiration: date
    next_expiration_dte: int
    open_profit_loss: Decimal
    premium_capture_percent: Decimal
    theta_estimate_per_day: Decimal


@dataclass(frozen=True, slots=True)
class OpenPutRow:
    option_symbol: str
    symbol: str
    contracts: int
    strike: Decimal
    sold_on: date | None
    expires_on: date
    original_days_to_expiration: int | None
    days_to_expiration: int
    obligated_shares: int
    assignment_notional: Decimal
    strike_distance_per_share: Decimal
    strike_distance_percent: Decimal
    strike_distance_display: Decimal
    strike_distance_percent_display: Decimal
    strike_state_label: str
    strike_distance_available: bool
    entry_credit_per_share: Decimal
    effective_entry_per_share: Decimal | None
    entry_credit: Decimal
    current_liability: Decimal
    estimated_close_cost: Decimal
    close_cost_basis: str
    open_profit_loss: Decimal
    theta_estimate_per_day: Decimal
    elapsed_time_percent: Decimal | None
    time_remaining_percent: Decimal | None
    credit_capture_percent: Decimal
    option_value_vs_credit_percent: Decimal
    option_value_track_percent: Decimal
    option_value_overrun_percent: Decimal
    decay_stage: str
    bid_per_share: Decimal
    mark_per_share: Decimal
    close_ask_per_share: Decimal
    spread_per_share: Decimal
    implied_volatility_percent: Decimal | None
    delta: Decimal | None
    gamma: Decimal | None
    theta_per_share: Decimal | None
    vega: Decimal | None
    position_delta_share_equivalent: Decimal | None
    position_gamma_delta_change_per_dollar: Decimal | None
    position_vega_per_volatility_point: Decimal | None
    price_time_read: PriceTimeRead
    volume: int | None
    open_interest: int | None
    intrinsic_value: Decimal
    remaining_extrinsic_value: Decimal
    quote_status: str
    quote_observed_at: datetime | None
    quote_observed_on: date | None
    session_state: OptionSessionState
    session_label: str
    can_close_or_roll: bool


@dataclass(frozen=True, slots=True)
class OpenBookProjection:
    rows: tuple[OpenCallRow, ...]
    groups: tuple[OpenCallGroup, ...]
    put_rows: tuple[OpenPutRow, ...]
    total_positions: int
    total_contracts: int
    call_contracts: int
    put_contracts: int
    obligated_shares: int
    entry_credit: Decimal
    current_liability: Decimal
    open_profit_loss: Decimal
    theta_estimate_per_day: Decimal
    same_day_theta_estimate_per_day: Decimal
    later_theta_estimate_per_day: Decimal
    pending_settlement_positions: int
    pending_settlement_contracts: int
    risk: OpenRiskSummary | None


@dataclass(frozen=True, slots=True)
class VolatilityRow:
    symbol: str
    sessions: int
    realized_volatility_percent: Decimal | None
    open_call_iv_percent: Decimal
    implied_minus_realized_points: Decimal | None
    iv_rank_percent: Decimal | None
    range_position_percent: Decimal
    thirteen_week_change_percent: Decimal
    strike_buffer_percent: Decimal
    quality: str


def build_open_book(snapshot: DashboardSnapshot) -> OpenBookProjection:
    policy_by_id = {
        policy.policy_id: policy
        for underlying_policy in snapshot.policies
        for policy in underlying_policy.policies
    }
    groups: list[OpenCallGroup] = []
    for underlying in snapshot.underlyings:
        underlying_rows = tuple(
            sorted(
                (
                    _open_call_row(
                        underlying,
                        clock,
                        policy=policy_by_id.get(clock.policy_id),
                    )
                    for clock in underlying.open_call_clocks
                ),
                key=lambda row: (row.expires_on, row.strike),
            )
        )
        if not underlying_rows:
            continue
        actionable_rows = tuple(row for row in underlying_rows if row.can_close_or_roll)
        summary_rows = actionable_rows or underlying_rows
        nearest = min(summary_rows, key=lambda row: abs(row.strike_distance_percent))
        next_expiring = min(summary_rows, key=lambda row: row.expires_on)
        entry_credit = sum((row.entry_credit for row in underlying_rows), Decimal(0))
        current_liability = sum((row.current_liability for row in underlying_rows), Decimal(0))
        groups.append(
            OpenCallGroup(
                symbol=underlying.symbol,
                rows=underlying_rows,
                position_count=len(underlying_rows),
                contract_count=sum((row.contracts for row in underlying_rows), 0),
                nearest_buffer_percent=nearest.strike_distance_percent,
                next_expiration=next_expiring.expires_on,
                next_expiration_dte=next_expiring.days_to_expiration,
                open_profit_loss=sum((row.open_profit_loss for row in underlying_rows), Decimal(0)),
                premium_capture_percent=(
                    (entry_credit - current_liability) / entry_credit * Decimal("100")
                    if entry_credit
                    else Decimal(0)
                ),
                theta_estimate_per_day=sum(
                    (row.theta_estimate_per_day for row in underlying_rows), Decimal(0)
                ),
            )
        )
    grouped_rows = tuple(row for group in groups for row in group.rows)
    put_rows = tuple(
        _open_put_row(put)
        for put in (
            snapshot.live_position_book.puts if snapshot.live_position_book is not None else ()
        )
    )
    call_contracts = sum((row.contracts for row in grouped_rows), 0)
    put_contracts = sum((row.contracts for row in put_rows), 0)
    all_rows = grouped_rows + put_rows
    theta_estimate_per_day = sum((row.theta_estimate_per_day for row in all_rows), Decimal(0))
    same_day_theta_estimate_per_day = sum(
        (row.theta_estimate_per_day for row in all_rows if row.days_to_expiration == 0),
        Decimal(0),
    )
    return OpenBookProjection(
        rows=grouped_rows,
        groups=tuple(groups),
        put_rows=put_rows,
        total_positions=len(grouped_rows) + len(put_rows),
        total_contracts=call_contracts + put_contracts,
        call_contracts=call_contracts,
        put_contracts=put_contracts,
        obligated_shares=sum((row.obligated_shares for row in grouped_rows), 0)
        + sum((row.obligated_shares for row in put_rows), 0),
        entry_credit=sum((row.entry_credit for row in grouped_rows), Decimal(0))
        + sum((row.entry_credit for row in put_rows), Decimal(0)),
        current_liability=sum((row.current_liability for row in grouped_rows), Decimal(0))
        + sum((row.current_liability for row in put_rows), Decimal(0)),
        open_profit_loss=sum((row.open_profit_loss for row in grouped_rows), Decimal(0))
        + sum((row.open_profit_loss for row in put_rows), Decimal(0)),
        theta_estimate_per_day=theta_estimate_per_day,
        same_day_theta_estimate_per_day=same_day_theta_estimate_per_day,
        later_theta_estimate_per_day=(theta_estimate_per_day - same_day_theta_estimate_per_day),
        pending_settlement_positions=sum(not row.can_close_or_roll for row in all_rows),
        pending_settlement_contracts=sum(
            row.contracts for row in all_rows if not row.can_close_or_roll
        ),
        risk=build_open_risk_summary(snapshot),
    )


def _open_put_row(option: LiveOpenOptionPosition) -> OpenPutRow:
    multiplier = abs(option.contract_multiplier or Decimal("100"))
    entry_credit_per_share = abs(option.entry_credit_per_share or Decimal(0))
    entry_credit_available = option.entry_credit_per_share is not None
    entry_credit = entry_credit_per_share * multiplier * Decimal(option.contracts)
    obligated_shares = int(multiplier * Decimal(option.contracts))
    strike_distance_available = (
        option.strike_distance_per_share is not None and option.strike_distance_percent is not None
    )
    strike_distance_per_share = option.strike_distance_per_share or Decimal(0)
    strike_distance_percent = option.strike_distance_percent or Decimal(0)
    if not strike_distance_available:
        strike_state_label = "MARK UNAVAILABLE"
    elif strike_distance_per_share > 0:
        strike_state_label = "OTM BUFFER"
    elif strike_distance_per_share < 0:
        strike_state_label = "ITM BY"
    else:
        strike_state_label = "AT STRIKE"
    current_liability = abs(
        option.market_value
        if option.market_value is not None
        else (option.estimated_mark_per_share or Decimal(0))
        * multiplier
        * Decimal(option.contracts)
    )
    close_basis_value = (
        option.ask_per_share
        if option.ask_per_share is not None
        else option.estimated_mark_per_share
    )
    estimated_close_cost = abs(
        (close_basis_value or Decimal(0)) * multiplier * Decimal(option.contracts)
    )
    mark_per_share = abs(option.estimated_mark_per_share or Decimal(0))
    bid_per_share = abs(option.bid_per_share or mark_per_share)
    close_ask_per_share = abs(option.ask_per_share or mark_per_share)
    spread_per_share = max(Decimal(0), close_ask_per_share - bid_per_share)
    theta_estimate_per_day = (
        -(option.theta_per_share or Decimal(0)) * multiplier * Decimal(option.contracts)
        if option.can_close_or_roll
        else Decimal(0)
    )
    option_value_vs_credit_percent = (
        current_liability / entry_credit * Decimal("100") if entry_credit else Decimal(0)
    )
    credit_capture_percent = (
        (entry_credit - current_liability) / entry_credit * Decimal("100")
        if entry_credit
        else Decimal(0)
    )
    option_value_track_percent = min(
        Decimal("100"), max(Decimal(0), option_value_vs_credit_percent)
    )
    option_value_overrun_percent = max(
        Decimal(0), option_value_vs_credit_percent - Decimal("100")
    )
    original_days_to_expiration = option.original_days_to_expiration
    elapsed_time_percent: Decimal | None = None
    time_remaining_percent: Decimal | None = None
    if option.opened_on is not None and original_days_to_expiration is not None:
        elapsed_days = max(
            0,
            (option.expires_on - option.opened_on).days - option.days_to_expiration,
        )
        if original_days_to_expiration > 0:
            elapsed_time_percent = min(
                Decimal("100"),
                Decimal(elapsed_days) / Decimal(original_days_to_expiration) * Decimal("100"),
            )
            time_remaining_percent = max(
                Decimal(0), Decimal("100") - elapsed_time_percent
            )
        else:
            elapsed_time_percent = Decimal("100")
            time_remaining_percent = Decimal(0)
    intrinsic_per_share = max(
        Decimal(0), option.strike - (option.underlying_price or option.strike)
    )
    intrinsic_value = intrinsic_per_share * multiplier * Decimal(option.contracts)
    remaining_extrinsic_value = max(Decimal(0), current_liability - intrinsic_value)
    return OpenPutRow(
        option_symbol=option.option_symbol,
        symbol=option.underlying_symbol,
        contracts=option.contracts,
        strike=option.strike,
        sold_on=option.opened_on,
        expires_on=option.expires_on,
        original_days_to_expiration=original_days_to_expiration,
        days_to_expiration=option.days_to_expiration,
        obligated_shares=obligated_shares,
        assignment_notional=option.strike * multiplier * Decimal(option.contracts),
        strike_distance_per_share=strike_distance_per_share,
        strike_distance_percent=strike_distance_percent,
        strike_distance_display=abs(strike_distance_per_share),
        strike_distance_percent_display=abs(strike_distance_percent),
        strike_state_label=strike_state_label,
        strike_distance_available=strike_distance_available,
        entry_credit_per_share=entry_credit_per_share,
        effective_entry_per_share=(
            max(Decimal(0), option.strike - entry_credit_per_share)
            if entry_credit_available
            else None
        ),
        entry_credit=entry_credit,
        current_liability=current_liability,
        estimated_close_cost=estimated_close_cost,
        close_cost_basis="ASK" if option.ask_per_share is not None else "MARK ESTIMATE",
        open_profit_loss=option.open_profit_loss or Decimal(0),
        theta_estimate_per_day=theta_estimate_per_day,
        elapsed_time_percent=elapsed_time_percent,
        time_remaining_percent=time_remaining_percent,
        credit_capture_percent=credit_capture_percent,
        option_value_vs_credit_percent=option_value_vs_credit_percent,
        option_value_track_percent=option_value_track_percent,
        option_value_overrun_percent=option_value_overrun_percent,
        decay_stage=_put_decay_stage(
            option.days_to_expiration,
            elapsed_time_percent,
            session_label=option.session_label,
            can_close_or_roll=option.can_close_or_roll,
        ),
        bid_per_share=bid_per_share,
        mark_per_share=mark_per_share,
        close_ask_per_share=close_ask_per_share,
        spread_per_share=spread_per_share,
        implied_volatility_percent=option.implied_volatility_percent,
        delta=option.delta,
        gamma=option.gamma,
        theta_per_share=option.theta_per_share,
        vega=option.vega,
        position_delta_share_equivalent=option.position_delta_share_equivalent,
        position_gamma_delta_change_per_dollar=option.position_gamma_delta_change_per_dollar,
        position_vega_per_volatility_point=option.position_vega_per_volatility_point,
        price_time_read=option.price_time_read,
        volume=option.volume,
        open_interest=option.open_interest,
        intrinsic_value=intrinsic_value,
        remaining_extrinsic_value=remaining_extrinsic_value,
        quote_status=option.quote_quality or "UNKNOWN",
        quote_observed_at=option.quote_observed_at,
        quote_observed_on=(
            option.quote_observed_at.date() if option.quote_observed_at is not None else None
        ),
        session_state=option.session_state,
        session_label=option.session_label,
        can_close_or_roll=option.can_close_or_roll,
    )


def _put_decay_stage(
    days_to_expiration: int,
    elapsed_time_percent: Decimal | None,
    *,
    session_label: str,
    can_close_or_roll: bool,
) -> str:
    if not can_close_or_roll:
        return session_label
    if days_to_expiration <= 7:
        return "EXPIRING SOON"
    if elapsed_time_percent is None:
        return "OPEN TERM"
    if elapsed_time_percent < Decimal("33"):
        return "EARLY CYCLE"
    if elapsed_time_percent < Decimal("70"):
        return "MID CYCLE"
    return "LATE CYCLE"


def _open_call_row(
    underlying: UnderlyingCallStats,
    clock: OpenCallClock,
    *,
    policy: CallPolicy | None,
) -> OpenCallRow:
    if policy is None:
        policy_label = "Observed position"
        intent_label = "NO SAVED PLAN"
        fit_summary = "Not evaluated"
        policy_fits = True
    else:
        entry_buffer = (
            (clock.strike / clock.underlying_at_sale - 1) * Decimal("100")
            if clock.underlying_at_sale
            else Decimal("0")
        )
        fit = evaluate_policy_fit(
            policy,
            strike_buffer_percent=entry_buffer,
            days_to_expiration=clock.original_days_to_expiration,
            effective_exit_price=clock.strike + clock.entry_credit_per_share,
        )
        policy_label = policy.label
        intent_label = policy.intent.label
        fit_summary = fit.summary
        policy_fits = fit.fits
    option_value_track_percent = min(
        Decimal("100"), max(Decimal(0), clock.option_value_vs_credit_percent)
    )
    option_value_overrun_percent = max(
        Decimal(0), clock.option_value_vs_credit_percent - Decimal("100")
    )
    return OpenCallRow(
        record_id=clock.record_id,
        campaign_id=clock.campaign_id,
        symbol=underlying.symbol,
        contracts=clock.contracts,
        strike=clock.strike,
        sold_on=clock.sold_on,
        expires_on=clock.expires_on,
        original_days_to_expiration=clock.original_days_to_expiration,
        days_to_expiration=clock.days_to_expiration,
        obligated_shares=clock.obligated_shares,
        strike_distance_per_share=clock.strike_distance_per_share,
        strike_distance_percent=clock.strike_distance_percent,
        entry_credit=clock.entry_credit,
        current_liability=clock.current_option_value,
        open_profit_loss=clock.open_profit_loss,
        theta_estimate_per_day=clock.short_theta_per_day,
        elapsed_time_percent=clock.elapsed_time_percent,
        time_remaining_percent=clock.time_remaining_percent,
        credit_capture_percent=clock.credit_capture_percent,
        option_value_vs_credit_percent=clock.option_value_vs_credit_percent,
        option_value_track_percent=option_value_track_percent,
        option_value_overrun_percent=option_value_overrun_percent,
        decay_stage=clock.decay_stage,
        policy_label=policy_label,
        intent_label=intent_label,
        policy_fit_summary=fit_summary,
        policy_fits=policy_fits,
        entry_credit_per_share=clock.entry_credit_per_share,
        bid_per_share=clock.bid_per_share,
        mark_per_share=clock.mark_per_share,
        close_ask_per_share=clock.close_ask_per_share,
        spread_per_share=clock.spread_per_share,
        quote_status=clock.quote_status,
        quote_observed_on=clock.quote_observed_on,
        implied_volatility_percent=clock.implied_volatility_percent,
        delta=clock.delta,
        gamma=clock.gamma,
        theta_per_share=clock.theta_per_share,
        vega=clock.vega,
        position_delta_share_equivalent=clock.position_delta_share_equivalent,
        position_gamma_delta_change_per_dollar=clock.position_gamma_delta_change_per_dollar,
        position_vega_per_volatility_point=clock.position_vega_per_volatility_point,
        price_time_read=_clock_price_time_read(underlying, clock),
        volume=clock.volume,
        open_interest=clock.open_interest,
        intrinsic_value=clock.intrinsic_value,
        remaining_extrinsic_value=clock.remaining_extrinsic_value,
        next_event_label=_next_event_label(underlying, clock.expires_on),
        session_state=clock.session_state,
        session_label=clock.session_label,
        can_close_or_roll=clock.can_close_or_roll,
    )


def _clock_price_time_read(
    underlying: UnderlyingCallStats,
    clock: OpenCallClock,
) -> PriceTimeRead:
    """Keep the workspace consequence read available for demo and live clocks."""

    if clock.price_time_read is not None:
        return clock.price_time_read
    points = underlying.price_points
    return build_price_time_read(
        position_delta=clock.position_delta_share_equivalent,
        position_gamma=clock.position_gamma_delta_change_per_dollar,
        theta_per_day=clock.short_theta_per_day if clock.can_close_or_roll else None,
        current_underlying_price=underlying.current_price,
        previous_close=points[-2].price if len(points) >= 2 else None,
        weekly_reference_price=points[-6].price if len(points) >= 6 else None,
    )


def _next_event_label(underlying: UnderlyingCallStats, expires_on: date) -> str:
    ex_dividend = underlying.next_ex_dividend_date
    if ex_dividend is not None and ex_dividend <= expires_on:
        return f"EX-DIV {ex_dividend:%b %d} BEFORE EXPIRY"
    return "EARNINGS DATE UNAVAILABLE"


def build_volatility_rows(snapshot: DashboardSnapshot) -> tuple[VolatilityRow, ...]:
    rows: list[VolatilityRow] = []
    for underlying in snapshot.underlyings:
        observations = tuple(
            DailyVolatilityObservation(
                source_id=f"{snapshot.mode}:{underlying.symbol}:{point.date.isoformat()}",
                session_date=point.date,
                observed_at=datetime.combine(
                    point.date,
                    time(21, 0),
                    tzinfo=snapshot.as_of.tzinfo or UTC,
                ),
                close=point.price,
                normalized_implied_volatility=(
                    underlying.average_open_call_iv_percent
                    if point is underlying.price_points[-1]
                    else None
                ),
            )
            for point in underlying.price_points
        )
        summary = analyze_volatility_history(observations)
        realized_percent = (
            summary.annualized_realized_volatility * Decimal(100)
            if summary.annualized_realized_volatility is not None
            else None
        )
        iv_spread = (
            underlying.average_open_call_iv_percent - realized_percent
            if realized_percent is not None
            else None
        )
        rows.append(
            VolatilityRow(
                symbol=underlying.symbol,
                sessions=summary.observation_count,
                realized_volatility_percent=realized_percent,
                open_call_iv_percent=underlying.average_open_call_iv_percent,
                implied_minus_realized_points=iv_spread,
                iv_rank_percent=summary.implied_volatility_rank_percent,
                range_position_percent=underlying.range_position_percent,
                thirteen_week_change_percent=underlying.thirteen_week_change_percent,
                strike_buffer_percent=underlying.current_strike_buffer_percent,
                quality=summary.context.quality.value,
            )
        )
    return tuple(rows)
