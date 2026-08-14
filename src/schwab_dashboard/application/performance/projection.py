from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from schwab_dashboard.application.performance.baselines import (
    build_market_price_reference,
    build_static_share_baseline,
)
from schwab_dashboard.application.performance.models import (
    ComparisonSeries,
    PerformanceComparison,
)
from schwab_dashboard.application.performance.overlay import build_executed_option_overlay
from schwab_dashboard.application.performance.returns import build_time_weighted_returns

ZERO = Decimal("0")


def build_performance_comparison(
    *,
    balance_history: Sequence[dict[str, Any]],
    cash_movements: Sequence[dict[str, Any]],
    position_history: Sequence[dict[str, Any]] = (),
    daily_bars: Sequence[dict[str, Any]] = (),
    executions: Sequence[dict[str, Any]] = (),
) -> PerformanceComparison:
    actual_points = build_time_weighted_returns(balance_history, cash_movements)
    calculated = tuple(
        point for point in actual_points if point.cumulative_return_percent is not None
    )
    actual_return = calculated[-1].cumulative_return_percent if calculated else None
    external_flows = sum((point.external_flow for point in actual_points), ZERO)
    shares_baseline = build_static_share_baseline(
        position_history=position_history,
        daily_bars=daily_bars,
        cash_movements=cash_movements,
        actual_points=actual_points,
    )
    option_overlay = build_executed_option_overlay(
        executions=executions,
        actual_points=actual_points,
    )
    market_reference = build_market_price_reference(
        daily_bars=daily_bars,
        actual_points=actual_points,
    )
    warnings: list[str] = []
    if len(calculated) < 2:
        warnings.append(
            "At least two valued market days are needed for a meaningful chained return."
        )
    if external_flows:
        warnings.append("Deposits and withdrawals are excluded before returns are chained.")
    return PerformanceComparison(
        methodology_version="incoooming-twr-v1",
        range_label=(
            f"{actual_points[0].date:%b %d}-{actual_points[-1].date:%b %d, %Y}"
            if actual_points
            else "No daily valuation history"
        ),
        coverage_start=actual_points[0].date if actual_points else None,
        coverage_end=actual_points[-1].date if actual_points else None,
        external_flows_excluded=external_flows,
        actual=ComparisonSeries(
            key="actual",
            label="Managed book",
            status="ready" if actual_return is not None else "waiting",
            return_percent=actual_return,
            method_note="Daily time-weighted return from broker net-liquidation snapshots.",
            points=actual_points,
        ),
        shares_without_options=shares_baseline,
        option_overlay=option_overlay,
        market_reference=market_reference,
        warnings=tuple(warnings),
    )
