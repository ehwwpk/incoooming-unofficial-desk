from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from schwab_dashboard.application.performance.assignments import (
    calculate_assignment_impact,
)
from schwab_dashboard.application.performance.baselines import (
    build_levered_market_baseline,
    build_market_price_reference,
    build_static_share_baseline,
)
from schwab_dashboard.application.performance.capital import calculate_capital_efficiency
from schwab_dashboard.application.performance.economics import calculate_option_economics
from schwab_dashboard.application.performance.models import (
    BenchmarkPolicyItem,
    ComparisonSeries,
    ManagementEdge,
    MatchedComparison,
    PerformanceComparison,
    PerformanceSpine,
)
from schwab_dashboard.application.performance.overlay import build_executed_option_overlay
from schwab_dashboard.application.performance.returns import build_time_weighted_returns
from schwab_dashboard.application.performance.risk import calculate_risk_statistics
from schwab_dashboard.application.performance.sessions import build_market_calendar

ZERO = Decimal("0")


def _last_valued_date(series: ComparisonSeries) -> date | None:
    return next(
        (
            point.date
            for point in reversed(series.points)
            if point.cumulative_return_percent is not None
        ),
        None,
    )


def _return_on(series: ComparisonSeries, as_of: date) -> Decimal | None:
    return next(
        (
            point.cumulative_return_percent
            for point in reversed(series.points)
            if point.date <= as_of and point.cumulative_return_percent is not None
        ),
        None,
    )


def _matched_comparison(
    *,
    actual: ComparisonSeries,
    shares: ComparisonSeries,
    market: ComparisonSeries,
    levered_market: ComparisonSeries,
) -> MatchedComparison:
    """Read every comparable series on the last session all of them reach."""

    ends = [
        day
        for day in (
            _last_valued_date(actual),
            _last_valued_date(shares),
            _last_valued_date(market),
            _last_valued_date(levered_market),
        )
        if day is not None
    ]
    if not ends:
        return MatchedComparison(
            status="not_available",
            as_of=None,
            managed_return_percent=None,
            shares_return_percent=None,
            market_return_percent=None,
            levered_market_return_percent=None,
            method_note="No series has a chained return yet, so no shared date exists.",
        )
    as_of = min(ends)
    return MatchedComparison(
        status="matched",
        as_of=as_of,
        managed_return_percent=_return_on(actual, as_of),
        shares_return_percent=_return_on(shares, as_of),
        market_return_percent=_return_on(market, as_of),
        levered_market_return_percent=_return_on(levered_market, as_of),
        method_note=(
            f"Every series is read on {as_of:%b %d, %Y}, the last session all of them cover. "
            "Price-derived series cannot extend past the latest published close, so comparing "
            "each series' own final value would credit management with unmatched market days."
        ),
    )


def build_performance_comparison(
    *,
    balance_history: Sequence[dict[str, Any]],
    cash_movements: Sequence[dict[str, Any]],
    position_history: Sequence[dict[str, Any]] = (),
    daily_bars: Sequence[dict[str, Any]] = (),
    executions: Sequence[dict[str, Any]] = (),
    lifecycle_events: Sequence[dict[str, Any]] = (),
    margin_interest_rate_percent: Decimal = Decimal("11"),
) -> PerformanceComparison:
    calendar = build_market_calendar(daily_bars)
    actual_points = build_time_weighted_returns(
        balance_history,
        cash_movements,
        calendar=calendar,
    )
    calculated = tuple(point for point in actual_points if point.daily_return_percent is not None)
    actual_return = actual_points[-1].cumulative_return_percent if actual_points else None
    external_flows = sum((point.external_flow for point in actual_points), ZERO)
    shares_baseline = build_static_share_baseline(
        position_history=position_history,
        daily_bars=daily_bars,
        cash_movements=cash_movements,
        actual_points=actual_points,
        executions=executions,
        lifecycle_events=lifecycle_events,
        annual_interest_rate_percent=margin_interest_rate_percent,
    )
    option_overlay = build_executed_option_overlay(
        executions=executions,
        actual_points=actual_points,
    )
    market_reference = build_market_price_reference(
        daily_bars=daily_bars,
        actual_points=actual_points,
    )
    levered_market_reference = build_levered_market_baseline(
        position_history=position_history,
        daily_bars=daily_bars,
        cash_movements=cash_movements,
        actual_points=actual_points,
        annual_interest_rate_percent=margin_interest_rate_percent,
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
    matched = _matched_comparison(
        actual=ComparisonSeries(
            key="actual",
            label="Managed book",
            status="ready" if actual_return is not None else "waiting",
            return_percent=actual_return,
            method_note="",
            points=actual_points,
        ),
        shares=shares_baseline,
        market=market_reference,
        levered_market=levered_market_reference,
    )
    management_difference = (
        matched.managed_return_percent - matched.shares_return_percent
        if matched.managed_return_percent is not None and matched.shares_return_percent is not None
        else None
    )
    management_edge = ManagementEdge(
        status="derived" if management_difference is not None else "not_available",
        return_difference_percent=management_difference,
        method_note=(
            "Managed TWR minus starting stock plus your share trades, no overlay, both read on "
            f"{matched.as_of:%b %d, %Y} because that is the last session both series cover. "
            "This is versus that freeze, not overlay alpha, not a sleeve grade."
            if management_difference is not None and matched.as_of is not None
            else "A matched starting-share counterfactual is required before a difference is shown."
        ),
    )
    benchmark_policy = (
        BenchmarkPolicyItem(
            key="same_underlyings",
            label="Starting stock plus your share trades",
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
            key="leverage_matched_market",
            label="Market at matched exposure",
            role="LEVERAGE CONTROL",
            status=levered_market_reference.status,
            method_note=levered_market_reference.method_note,
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
        methodology_version="incoooming-performance-v5",
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
        levered_market_reference=levered_market_reference,
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
        matched=matched,
    )
