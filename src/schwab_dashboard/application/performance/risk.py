from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from math import sqrt
from statistics import stdev

from schwab_dashboard.application.performance.models import ReturnPoint, RiskStatistics

ZERO = Decimal("0")
HUNDRED = Decimal("100")


def calculate_risk_statistics(points: Sequence[ReturnPoint]) -> RiskStatistics:
    returns = [
        point.daily_return_percent
        for point in points
        if point.daily_return_percent is not None
    ]
    measured_days = (points[-1].date - points[0].date).days + 1 if points else 0
    if len(returns) < 2:
        return RiskStatistics(
            status="waiting",
            observations=len(returns),
            measured_days=measured_days,
            max_drawdown_percent=None,
            annualized_volatility_percent=None,
            positive_day_percent=None,
            worst_day_percent=min(returns) if returns else None,
            method_note="At least two valued return days are needed for risk statistics.",
        )

    wealth = Decimal("1")
    peak = wealth
    max_drawdown = ZERO
    for daily_return in returns:
        wealth *= Decimal("1") + daily_return / HUNDRED
        peak = max(peak, wealth)
        drawdown = (wealth / peak - Decimal("1")) * HUNDRED
        max_drawdown = min(max_drawdown, drawdown)

    annualized_volatility = Decimal(
        str(stdev(float(item / HUNDRED) for item in returns) * sqrt(252) * 100)
    )
    positive_days = sum(item > ZERO for item in returns)
    status = "ready" if len(returns) >= 20 else "early_sample"
    note = (
        "Daily TWR observations; volatility uses sample standard deviation and 252 "
        "trading days."
        if status == "ready"
        else "Early sample: the same daily method is used, but fewer than 20 return days exist."
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
    )
