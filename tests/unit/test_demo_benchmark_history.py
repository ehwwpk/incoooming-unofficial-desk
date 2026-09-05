from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from statistics import median

import pytest

from schwab_dashboard.application.dashboard.cashflows import build_call_cash_events, cash_total
from schwab_dashboard.application.performance.periods import PerformancePeriod
from schwab_dashboard.application.performance.projection import build_performance_comparison
from schwab_dashboard.infrastructure.demo.fixtures.benchmark_history import (
    DEMO_PROVENANCE,
    build_demo_performance_comparison,
    build_demo_performance_history,
)
from schwab_dashboard.infrastructure.demo.fixtures.call_history import build_call_history
from schwab_dashboard.infrastructure.demo.fixtures.call_stats import (
    build_covered_call_summary,
    build_underlying_stats,
)
from schwab_dashboard.infrastructure.demo.fixtures.campaigns import build_campaigns
from schwab_dashboard.infrastructure.demo.fixtures.performance_charts import build_cash_chart_series
from schwab_dashboard.infrastructure.demo.fixtures.performance_ledger import (
    build_monthly_performance,
)
from schwab_dashboard.infrastructure.demo.fixtures.performance_operator import (
    build_operator_metrics,
)
from schwab_dashboard.infrastructure.demo.fixtures.performance_windows import (
    build_performance_windows,
)
from schwab_dashboard.infrastructure.demo.fixtures.policies import build_policies
from schwab_dashboard.infrastructure.demo.fixtures.positions import build_positions
from schwab_dashboard.infrastructure.demo.fixtures.short_puts import (
    build_put_cash_events,
    build_put_executions,
)

D = Decimal
AS_OF = date(2026, 8, 7)


def _inputs():
    return {
        "positions": build_positions(),
        "cash_value": D("18750"),
        "call_history": build_call_history(),
        "as_of": AS_OF,
        "put_executions": build_put_executions(),
    }


def test_every_demo_session_and_final_position_reconciles() -> None:
    inputs = _inputs()
    history = build_demo_performance_history(**inputs)
    assert history == build_demo_performance_history(**inputs)
    for balance in history.balance_history:
        rows = [
            row for row in history.position_history if row["observed_at"] == balance["observed_at"]
        ]
        assert (
            sum((row["market_value"] for row in rows), D("0")) + balance["cash_balance"]
            == balance["liquidation_value"]
        )
        assert all(row["net_quantity"] >= 0 for row in rows if row["asset_type"] == "EQUITY")
        assert balance["cash_balance"] >= 0
        for equity in (row for row in rows if row["asset_type"] == "EQUITY"):
            obligated_shares = sum(
                abs(row["net_quantity"]) * D("100")
                for row in rows
                if row["asset_type"] == "OPTION"
                and row["option_side"] == "CALL"
                and row["underlying_symbol"] == equity["symbol"]
            )
            assert obligated_shares <= equity["net_quantity"]
        put_collateral = sum(
            abs(row["net_quantity"]) * row["strike"] * D("100")
            for row in rows
            if row["asset_type"] == "OPTION" and row["option_side"] == "PUT"
        )
        assert balance["cash_balance"] >= put_collateral
    latest = {row["symbol"]: row for row in rows}
    for position in inputs["positions"]:
        assert latest[position.symbol]["net_quantity"] == position.quantity
        assert latest[position.symbol]["market_value"] == position.market_value
    assert history.balance_history[-1]["cash_balance"] == inputs["cash_value"]
    assert history.balance_history[-1]["available_funds"] == D("7250")
    assert history.balance_history[-1]["buying_power"] == D("14500")


def test_demo_reuses_production_returns_and_never_hides_fictional_provenance() -> None:
    inputs = _inputs()
    history = build_demo_performance_history(**inputs)
    actual = build_demo_performance_comparison(**inputs)
    expected = build_performance_comparison(
        balance_history=history.balance_history,
        position_history=history.position_history,
        cash_movements=history.cash_movements,
        daily_bars=history.daily_bars,
        executions=history.executions,
        lifecycle_events=history.lifecycle_events,
    )
    assert actual.actual.points == expected.actual.points
    assert actual.matched.status == "matched"
    assert actual.matched.as_of == AS_OF
    assert actual.warnings[0] == DEMO_PROVENANCE
    for series in (
        actual.actual,
        actual.shares_without_options,
        actual.market_reference,
        actual.levered_market_reference,
    ):
        assert len(series.points) >= 50
        assert series.return_percent is not None
        assert "FICTIONAL DEMO" in series.method_note
        assert series.points[-1].date == AS_OF
    assert actual.spine.risk.status == "ready"
    assert actual.spine.risk.max_drawdown_percent < 0
    assert actual.spine.risk.worst_day_percent < 0
    assert actual.spine.risk.annualized_volatility_percent > 0
    assert actual.spine.option_economics.campaign_cash_variance == 0
    assert actual.spine.option_economics.status == "reconciled"
    assert actual.spine.assignment_impact.called_away_shares == D("200")
    assert actual.spine.capital_efficiency.latest_net_liquidation == sum(
        (item.market_value for item in inputs["positions"]), inputs["cash_value"]
    )


def test_fictional_deposit_is_excluded_and_not_promoted_to_observed_daily_risk() -> None:
    comparison = build_demo_performance_comparison(**_inputs())
    assert comparison.external_flows_excluded == D("-45000")
    points = comparison.actual.points
    flow_points = [(i, point) for i, point in enumerate(points) if point.external_flow]
    assert [point.external_flow for _, point in flow_points] == [D("5000"), D("-50000")]
    for index, point in flow_points:
        previous = points[index - 1]
        expected = (point.value - previous.value - point.external_flow) / previous.value * D("100")
        assert abs(point.daily_return_percent - expected) < D("0.00000000000000000001")
        assert point.return_quality == "estimated"
    assert comparison.spine.risk.observations == len(points) - 3


@pytest.mark.parametrize("period", list(PerformancePeriod))
def test_demo_periods_recalculate_complete_inputs_at_a_shared_start(period) -> None:
    comparison = build_demo_performance_comparison(**_inputs(), period=period)
    start = period.starts_on(through=AS_OF)
    assert comparison.coverage_start >= (start or date.min)
    assert comparison.matched.as_of == AS_OF
    assert comparison.actual.points[0].daily_return_percent is None
    expected_cash = cash_total(
        (*build_call_cash_events(build_call_history()), *build_put_cash_events()),
        start=comparison.coverage_start,
        end=AS_OF,
    )
    assert comparison.spine.option_economics.net_executed_cash == expected_cash
    if period is PerformancePeriod.ONE_MONTH:
        assert comparison.coverage_start == date(2026, 7, 7)
        assert comparison.external_flows_excluded == D("-50000")


def test_missing_put_ledger_cannot_silently_omit_current_option_liability() -> None:
    inputs = _inputs()
    inputs["put_executions"] = ()
    with pytest.raises(ValueError, match="reconcile to current positions"):
        build_demo_performance_history(**inputs)


def test_rolls_remain_open_campaigns_in_both_demo_presentations() -> None:
    records = build_call_history()
    campaigns = build_campaigns(
        records, build_underlying_stats(records, AS_OF), build_policies(), AS_OF
    )
    completed = [campaign for campaign in campaigns if campaign.status != "OPEN"]
    comparison = build_demo_performance_comparison(**_inputs())
    economics = comparison.spine.option_economics
    assert economics.closed_campaigns == len(completed) == 7
    assert (
        economics.closed_campaign_result
        == sum((campaign.net_cash_to_date for campaign in completed), D("0"))
        == D("2830")
    )
    assert economics.campaign_cash_variance == D("0")


def test_demo_cash_windows_charts_months_and_benchmarks_share_one_option_ledger() -> None:
    records = build_call_history()
    monthly = build_monthly_performance()
    windows = build_performance_windows(records, D("206473"), AS_OF, monthly)
    charts = build_cash_chart_series(records, monthly, AS_OF)
    comparison = build_demo_performance_comparison(**_inputs())
    assert (
        next(window for window in windows if window.key == "quarter").option_cash
        == comparison.spine.option_economics.net_executed_cash
    )
    for window in windows:
        chart = next(chart for chart in charts if chart.key == window.key)
        assert sum((point.option_cash for point in chart.points), D("0")) == window.option_cash
    events = (*build_call_cash_events(records), *build_put_cash_events())
    august = next(item for item in monthly if item.label == "AUG")
    assert august.option_cash == cash_total(events, start=date(2026, 8, 1), end=AS_OF)


def test_full_month_statistics_exclude_partial_month_and_handle_even_samples() -> None:
    records = build_call_history()
    monthly = build_monthly_performance()
    underlyings = build_underlying_stats(records, AS_OF)
    summary = build_covered_call_summary(records, underlyings)
    windows = build_performance_windows(records, D("206473"), AS_OF, monthly)
    # Six complete observations ensure the median must average the middle pair.
    monthly = (replace(monthly[0], is_partial=True), *monthly[1:])
    metrics = build_operator_metrics(records, summary, windows, build_policies(), monthly)
    completed = [item.option_cash for item in monthly if not item.is_partial]
    assert metrics.completed_months == 6
    assert metrics.rolling_year_monthly_average == (sum(completed) / D(6)).quantize(D("0.01"))
    assert metrics.median_completed_month == median(completed)
