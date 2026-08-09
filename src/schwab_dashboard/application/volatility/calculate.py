from __future__ import annotations

from decimal import Decimal, localcontext
from itertools import pairwise

from schwab_dashboard.application.volatility.models import (
    DailyVolatilityObservation,
    VolatilitySummary,
)
from schwab_dashboard.domain.analytics import CalculationContext, DataQuality, ValueStatus

TRADING_SESSIONS = Decimal("252")
ONE_HUNDRED = Decimal("100")


def analyze_volatility_history(
    observations: tuple[DailyVolatilityObservation, ...],
) -> VolatilitySummary:
    if not observations:
        raise ValueError("at least one volatility observation is required")
    ordered = tuple(sorted(observations, key=lambda item: item.session_date))
    if len({item.session_date for item in ordered}) != len(ordered):
        raise ValueError("volatility observations must have unique session dates")
    returns = _log_returns(ordered)
    realized = _annualized_sample_volatility(returns)
    iv_values = tuple(
        item.normalized_implied_volatility
        for item in ordered
        if item.normalized_implied_volatility is not None
    )
    latest_iv = iv_values[-1] if iv_values else None
    iv_rank = _iv_rank(iv_values)
    iv_percentile = _iv_percentile(iv_values)
    return VolatilitySummary(
        observation_count=len(ordered),
        return_count=len(returns),
        annualized_realized_volatility=realized,
        latest_implied_volatility=latest_iv,
        implied_volatility_rank_percent=iv_rank,
        implied_volatility_percentile=iv_percentile,
        implied_minus_realized=(
            latest_iv - realized if latest_iv is not None and realized is not None else None
        ),
        context=CalculationContext(
            as_of=ordered[-1].observed_at,
            status=ValueStatus.DERIVED,
            method="daily-log-return-sample-volatility-and-midrank-iv-percentile",
            method_version="1.0.0",
            source_ids=tuple(item.source_id for item in ordered),
            quality=(
                DataQuality.COMPLETE
                if len(iv_values) == len(ordered) and len(returns) >= 2
                else DataQuality.PARTIAL
            ),
        ),
    )


def _log_returns(
    observations: tuple[DailyVolatilityObservation, ...],
) -> tuple[Decimal, ...]:
    with localcontext() as context:
        context.prec = 34
        return tuple(
            (current.close / previous.close).ln() for previous, current in pairwise(observations)
        )


def _annualized_sample_volatility(returns: tuple[Decimal, ...]) -> Decimal | None:
    if len(returns) < 2:
        return None
    with localcontext() as context:
        context.prec = 34
        mean = sum(returns, Decimal(0)) / Decimal(len(returns))
        variance = sum(((value - mean) ** 2 for value in returns), Decimal(0)) / Decimal(
            len(returns) - 1
        )
        return variance.sqrt() * TRADING_SESSIONS.sqrt()


def _iv_rank(values: tuple[Decimal, ...]) -> Decimal | None:
    if not values:
        return None
    low = min(values)
    high = max(values)
    if high == low:
        return None
    return (values[-1] - low) / (high - low) * ONE_HUNDRED


def _iv_percentile(values: tuple[Decimal, ...]) -> Decimal | None:
    if len(values) < 2:
        return None
    latest = values[-1]
    history = values[:-1]
    below = sum(1 for value in history if value < latest)
    equal = sum(1 for value in history if value == latest)
    midrank = Decimal(below) + Decimal(equal) / Decimal(2)
    return midrank / Decimal(len(history)) * ONE_HUNDRED
