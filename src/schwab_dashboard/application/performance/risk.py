from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from math import sqrt
from statistics import stdev

from schwab_dashboard.application.performance.models import ReturnPoint, RiskStatistics

ZERO = Decimal("0")
HUNDRED = Decimal("100")


def calculate_risk_statistics(points: Sequence[ReturnPoint]) -> RiskStatistics:
    eligible = [
        point
        for point in points
        if point.daily_return_percent is not None
        and (
            (point.return_quality == "observed" and point.session_span == 1)
            or (
                point.return_quality == "unresolved"
                and point.quality in {"observed", "linked"}
                and point.session_span == 0
            )
        )
    ]
    returns = [
        point.daily_return_percent for point in eligible if point.daily_return_percent is not None
    ]
    reconstructed = sum(
        point.daily_return_percent is not None
        and point.session_span == 1
        and point.return_quality in {"derived", "estimated"}
        for point in points
    )
    measured_days = sum(point.session_span == 1 for point in points)
    if len(returns) < 2:
        return RiskStatistics(
            status="waiting",
            observations=len(returns),
            measured_days=measured_days,
            max_drawdown_percent=None,
            annualized_volatility_percent=None,
            positive_day_percent=None,
            worst_day_percent=min(returns) if returns else None,
            method_note=(
                "At least two adjacent observed closing returns are needed. Reconstructed, "
                "provisional, and multi-session changes are excluded."
            ),
            reconstructed_observations=reconstructed,
        )

    max_drawdown = ZERO
    wealth = Decimal("1")
    peak = wealth
    previous_date = None
    for point in eligible:
        if previous_date is not None and point.previous_date != previous_date:
            wealth = Decimal("1")
            peak = wealth
        daily_return = point.daily_return_percent
        if daily_return is None:
            continue
        wealth *= Decimal("1") + daily_return / HUNDRED
        peak = max(peak, wealth)
        max_drawdown = min(max_drawdown, (wealth / peak - Decimal("1")) * HUNDRED)
        previous_date = point.date

    annualized_volatility = Decimal(
        str(stdev(float(item / HUNDRED) for item in returns) * sqrt(252) * 100)
    )
    positive_days = sum(item > ZERO for item in returns)
    status = "ready" if len(returns) >= 20 else "early_sample"
    note = (
        "Observed adjacent close-to-close TWR only; volatility uses sample standard "
        "deviation and 252 trading days."
        if status == "ready"
        else "Early sample: observed adjacent closes only; reconstructed and multi-session "
        "returns are excluded."
    )
    return RiskStatistics(
        status=status,
        observations=len(returns),
        measured_days=measured_days,
        max_drawdown_percent=max_drawdown,
        annualized_volatility_percent=annualized_volatility,
        positive_day_percent=Decimal(positive_days) / Decimal(len(returns)) * HUNDRED,
        worst_day_percent=min(returns),
        method_note=note,
        reconstructed_observations=reconstructed,
    )
