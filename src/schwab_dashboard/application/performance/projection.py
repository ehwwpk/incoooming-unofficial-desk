from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from schwab_dashboard.application.performance.assignments import (
    calculate_assignment_impact,
)
from schwab_dashboard.application.performance.baselines import (
    build_market_price_reference,
    build_static_share_baseline,
)
from schwab_dashboard.application.performance.capital import calculate_capital_efficiency
from schwab_dashboard.application.performance.economics import calculate_option_economics
from schwab_dashboard.application.performance.models import (
    BenchmarkPolicyItem,
    ComparisonSeries,
    ManagementEdge,
    PerformanceComparison,
    PerformanceSpine,
)
from schwab_dashboard.application.performance.overlay import build_executed_option_overlay
from schwab_dashboard.application.performance.returns import build_time_weighted_returns
from schwab_dashboard.application.performance.risk import calculate_risk_statistics

ZERO = Decimal("0")


def build_performance_comparison(
    *,
    balance_history: Sequence[dict[str, Any]],
    cash_movements: Sequence[dict[str, Any]],
    position_history: Sequence[dict[str, Any]] = (),
    daily_bars: Sequence[dict[str, Any]] = (),
    executions: Sequence[dict[str, Any]] = (),
    lifecycle_events: Sequence[dict[str, Any]] = (),
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
    coverage_start = actual_points[0].date if actual_points else None
    coverage_end = actual_points[-1].date if actual_points else None
    economics = calculate_option_economics(
        executions=executions,
        lifecycle_events=lifecycle_events,
        position_history=position_history,
        coverage_start=coverage_start,
        coverage_end=coverage_end,
    )
    management_difference = (
        actual_return - shares_baseline.return_percent
        if actual_return is not None and shares_baseline.return_percent is not None
        else None
    )
    management_edge = ManagementEdge(
        status="derived" if management_difference is not None else "not_available",
        return_difference_percent=management_difference,
        method_note=(
            "Managed TWR minus the frozen starting-share counterfactual over the same stored "
            "dates. This is a decision comparison, not manager alpha."
            if management_difference is not None
            else "A matched starting-share counterfactual is required before a difference is shown."
        ),
    )
    benchmark_policy = (
        BenchmarkPolicyItem(
            key="same_underlyings",
            label="Same starting shares",
            role="PRIMARY COUNTERFACTUAL",
            status=shares_baseline.status,
            method_note=shares_baseline.method_note,
        ),
        BenchmarkPolicyItem(
            key="market_total_return",
            label="Broad-market total return",
            role="MARKET BENCHMARK",
            status="not_stored",
            method_note=(
                "A matched total-return series is not stored yet. The SPY line remains price "
                "context and is not promoted to a total-return benchmark."
            ),
        ),
        BenchmarkPolicyItem(
            key="covered_call_index",
            label="Declared buy-write index",
            role="STRATEGY REFERENCE",
            status="not_stored",
            method_note=(
                "Cboe BXM/BXMD-style data must be stored for the same dates before a covered-call "
                "benchmark can be shown. No substitute series is fabricated."
            ),
        ),
    )
    warnings: list[str] = []
    if len(calculated) < 2:
        warnings.append(
            "At least two valued market days are needed for a meaningful chained return."
        )
    if external_flows:
        warnings.append("Deposits and withdrawals are excluded before returns are chained.")
    return PerformanceComparison(
        methodology_version="incoooming-performance-v2",
        range_label=(
            f"{actual_points[0].date:%b %d}-{actual_points[-1].date:%b %d, %Y}"
            if actual_points
            else "No daily valuation history"
        ),
        coverage_start=coverage_start,
        coverage_end=coverage_end,
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
        spine=PerformanceSpine(
            management_edge=management_edge,
            risk=calculate_risk_statistics(actual_points),
            option_economics=economics,
            capital_efficiency=calculate_capital_efficiency(
                actual_points=actual_points,
                balance_history=balance_history,
                net_option_cash=economics.net_executed_cash,
            ),
            assignment_impact=calculate_assignment_impact(
                lifecycle_events=lifecycle_events,
                daily_bars=daily_bars,
                coverage_start=coverage_start,
                coverage_end=coverage_end,
            ),
            benchmark_policy=benchmark_policy,
        ),
        warnings=tuple(warnings),
    )
