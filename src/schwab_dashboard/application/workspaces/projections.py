from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal

from schwab_dashboard.application.dashboard.models import DashboardSnapshot
from schwab_dashboard.application.volatility.calculate import analyze_volatility_history
from schwab_dashboard.application.volatility.models import DailyVolatilityObservation


@dataclass(frozen=True, slots=True)
class OpenCallRow:
    symbol: str
    contracts: int
    strike: Decimal
    expires_on: date
    days_to_expiration: int
    obligated_shares: int
    strike_distance_per_share: Decimal
    strike_distance_percent: Decimal
    entry_credit: Decimal
    current_liability: Decimal
    open_profit_loss: Decimal
    theta_estimate_per_day: Decimal
    elapsed_time_percent: Decimal
    decay_stage: str


@dataclass(frozen=True, slots=True)
class OpenBookProjection:
    rows: tuple[OpenCallRow, ...]
    obligated_shares: int
    entry_credit: Decimal
    current_liability: Decimal
    open_profit_loss: Decimal
    theta_estimate_per_day: Decimal


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
    rows = tuple(
        OpenCallRow(
            symbol=underlying.symbol,
            contracts=clock.contracts,
            strike=clock.strike,
            expires_on=clock.expires_on,
            days_to_expiration=clock.days_to_expiration,
            obligated_shares=clock.contracts * 100,
            strike_distance_per_share=clock.strike_distance_per_share,
            strike_distance_percent=clock.strike_distance_percent,
            entry_credit=clock.entry_credit,
            current_liability=clock.current_option_value,
            open_profit_loss=clock.open_profit_loss,
            theta_estimate_per_day=clock.short_theta_per_day,
            elapsed_time_percent=clock.elapsed_time_percent,
            decay_stage=clock.decay_stage,
        )
        for underlying in snapshot.underlyings
        for clock in underlying.open_call_clocks
    )
    return OpenBookProjection(
        rows=rows,
        obligated_shares=sum((row.obligated_shares for row in rows), 0),
        entry_credit=sum((row.entry_credit for row in rows), Decimal(0)),
        current_liability=sum((row.current_liability for row in rows), Decimal(0)),
        open_profit_loss=sum((row.open_profit_loss for row in rows), Decimal(0)),
        theta_estimate_per_day=sum(
            (row.theta_estimate_per_day for row in rows), Decimal(0)
        ),
    )


def build_volatility_rows(snapshot: DashboardSnapshot) -> tuple[VolatilityRow, ...]:
    rows: list[VolatilityRow] = []
    for underlying in snapshot.underlyings:
        observations = tuple(
            DailyVolatilityObservation(
                source_id=f"{snapshot.mode}:{underlying.symbol}:{point.date.isoformat()}",
                session_date=point.date,
                observed_at=datetime.combine(point.date, time(21, 0), tzinfo=snapshot.as_of.tzinfo),
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
