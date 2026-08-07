from decimal import Decimal

from schwab_dashboard.infrastructure.demo.dashboard import DemoDashboardReader


def test_demo_dashboard_is_internally_reconciled() -> None:
    snapshot = DemoDashboardReader().execute()

    assert snapshot.is_demo
    assert snapshot.portfolio.total_value == (
        snapshot.portfolio.stock_value
        + snapshot.portfolio.option_value
        + snapshot.portfolio.cash_value
    )
    assert sum(
        (allocation.percent for allocation in snapshot.allocations), Decimal("0")
    ) == Decimal("100.00")
    assert snapshot.risk.short_contracts == sum(
        int(abs(position.quantity))
        for position in snapshot.positions
        if position.asset_type == "OPTION" and position.quantity < 0
    )


def test_demo_income_period_totals_are_derived_from_components() -> None:
    snapshot = DemoDashboardReader().execute()

    assert len(snapshot.income_periods) == 13
    assert all(
        period.total == period.option_income + period.dividends
        for period in snapshot.income_periods
    )
    assert all(0 <= period.bar_percent <= 100 for period in snapshot.income_periods)
    assert sum((period.option_income for period in snapshot.income_periods), Decimal("0")) == (
        snapshot.covered_calls.net_option_cash
    )
    assert sum((period.dividends for period in snapshot.income_periods), Decimal("0")) == (
        snapshot.covered_calls.dividends
    )
