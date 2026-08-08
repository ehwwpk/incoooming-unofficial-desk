from decimal import Decimal

import pytest

from schwab_dashboard.application.dashboard.performance import calculate_capital_recovery
from schwab_dashboard.infrastructure.demo.dashboard import DemoDashboardReader

D = Decimal


def test_personalized_holdings_and_coverage_are_consistent() -> None:
    snapshot = DemoDashboardReader().execute()
    by_symbol = {item.symbol: item for item in snapshot.underlyings}

    assert {symbol: item.shares for symbol, item in by_symbol.items()} == {
        "CVX": 700,
        "KTOS": 800,
        "URNM": 500,
    }
    assert snapshot.covered_calls.total_shares == 2000
    assert snapshot.covered_calls.contract_capacity == 20
    assert snapshot.covered_calls.active_contracts == 18
    assert all(item.active_contracts <= item.contract_capacity for item in by_symbol.values())


def test_mock_calls_follow_requested_strike_and_expiration_guardrails() -> None:
    snapshot = DemoDashboardReader().execute()

    assert len(snapshot.call_history) == 16
    for record in snapshot.call_history:
        assert D("15") <= record.strike_upside_percent <= D("40")
        assert 21 <= record.days_to_expiration <= 56
        assert record.gross_premium == record.premium_per_share * record.contracts * 100
        assert record.net_cash == record.gross_premium - record.buyback_cost
        assert "low" not in record.sale_signal.lower()


def test_call_cash_and_lifecycle_reconcile_at_symbol_and_portfolio_level() -> None:
    snapshot = DemoDashboardReader().execute()
    calls = snapshot.covered_calls

    assert calls.gross_premium == D("9005.00")
    assert calls.buyback_cost == D("2665.00")
    assert calls.net_option_cash == D("6340.00")
    assert calls.dividends == D("1246.00")
    assert calls.total_cash_income == D("7586.00")
    assert calls.net_option_cash == calls.gross_premium - calls.buyback_cost
    assert calls.net_option_cash == sum(
        (item.net_option_cash for item in snapshot.underlyings), D("0")
    )
    assert calls.contracts_sold == (
        calls.expired_contracts
        + calls.closed_contracts
        + calls.rolled_contracts
        + calls.active_contracts
    )
    assert calls.called_away_shares == 0


def test_portfolio_value_reconciles_with_personalized_inventory() -> None:
    snapshot = DemoDashboardReader().execute()

    assert sum((item.market_value for item in snapshot.underlyings), D("0")) == (
        snapshot.portfolio.stock_value
    )
    assert snapshot.portfolio.total_value == (
        snapshot.portfolio.stock_value
        + snapshot.portfolio.option_value
        + snapshot.portfolio.cash_value
    )


def test_every_performance_window_reconciles_cash_and_goal_math() -> None:
    snapshot = DemoDashboardReader().execute()
    windows = {window.key: window for window in snapshot.performance_windows}

    assert tuple(windows) == ("week", "month", "quarter", "ytd", "r365")
    for window in windows.values():
        assert window.gross_premium - window.buyback_cost == window.option_cash
        assert window.option_cash + window.dividends == window.total_cash
        assert window.target_cash_for_window >= D("0")
        assert window.target_progress_percent >= D("0")
        expected_capture = (
            (window.option_cash / window.gross_premium * 100).quantize(D("0.1"))
            if window.gross_premium
            else D("0")
        )
        assert window.premium_capture_percent == expected_capture

    assert windows["quarter"].option_cash == snapshot.covered_calls.net_option_cash
    assert windows["quarter"].dividends == snapshot.covered_calls.dividends
    assert windows["r365"].target_cash_for_window == D("36000.00")
    assert windows["ytd"].monthly_option_run_rate > D("3000")
    assert windows["r365"].monthly_option_run_rate < D("3000")


def test_management_objective_exposes_inputs_instead_of_a_single_risk_score() -> None:
    snapshot = DemoDashboardReader().execute()
    objective = snapshot.objective

    assert objective.monthly_option_target == D("3000")
    assert objective.rolling_year_target_gap == (
        objective.monthly_option_target - objective.rolling_year_monthly_average
    )
    assert objective.premium_capture_percent + objective.buyback_drag_percent == D("100.0")
    assert objective.compliant_call_tickets == objective.total_call_tickets == 16
    assert objective.target_months_hit <= objective.observed_months
    assert sum(objective.monthly_option_results, D("0")) == D("31780")
    assert objective.target_months_hit == sum(
        1
        for result in objective.monthly_option_results
        if result >= objective.monthly_option_target
    )
    assert objective.uncovered_contract_capacity == (
        snapshot.covered_calls.contract_capacity - snapshot.covered_calls.active_contracts
    )


def test_lifetime_income_basis_lens_is_analytical_and_reconciled() -> None:
    snapshot = DemoDashboardReader().execute()
    portfolio, *symbols = snapshot.basis_lens

    for item in snapshot.basis_lens:
        assert item.lifetime_management_income == (
            item.lifetime_option_income + item.lifetime_dividends
        )
        assert item.income_adjusted_basis == (
            item.original_cost_basis - item.lifetime_management_income
        )
    assert portfolio.symbol == "PORT"
    assert portfolio.original_cost_basis == sum(
        (item.original_cost_basis for item in symbols), D("0")
    )
    assert portfolio.lifetime_management_income == sum(
        (item.lifetime_management_income for item in symbols), D("0")
    )
    assert portfolio.capital_remaining == portfolio.income_adjusted_basis
    assert portfolio.recovery_surplus == D("0")
    assert not portfolio.fully_recovered


def test_capital_recovery_switches_to_surplus_after_original_cost_is_earned_back() -> None:
    recovery = calculate_capital_recovery(D("100000"), D("127500"))

    assert recovery.income_adjusted_basis == D("-27500")
    assert recovery.capital_remaining == D("0")
    assert recovery.recovery_surplus == D("27500")
    assert recovery.recovered_percent == D("127.5")
    assert recovery.fully_recovered

    with pytest.raises(ValueError, match="Original cost basis"):
        calculate_capital_recovery(D("0"), D("100"))


def test_per_name_apr_iv_and_assignment_buffer_metrics_are_populated() -> None:
    snapshot = DemoDashboardReader().execute()

    for item in snapshot.underlyings:
        assert item.quarter_total_cash == item.net_option_cash + item.quarter_dividends
        assert item.quarter_option_apr > D("0")
        assert item.quarter_total_cash_apr >= item.quarter_option_apr
        assert item.average_open_call_iv_percent > D("0")
        assert D("0") < item.average_open_call_delta < D("0.5")
        assert item.current_strike_buffer_percent >= D("15")
        assert item.premium_capture_percent <= D("100")
        assert item.income_adjusted_basis_per_share < item.average_cost

    by_symbol = {item.symbol: item for item in snapshot.underlyings}
    assert by_symbol["CVX"].dividend_overlap_contracts == 6
    assert by_symbol["CVX"].next_ex_dividend_date is not None
    assert by_symbol["CVX"].dividend_per_share == D("1.78")
    assert by_symbol["KTOS"].dividend_overlap_contracts == 0
    assert by_symbol["URNM"].dividend_overlap_contracts == 0


def test_name_windows_reconcile_to_every_portfolio_window() -> None:
    snapshot = DemoDashboardReader().execute()
    portfolio_windows = {window.key: window for window in snapshot.performance_windows}

    for key, portfolio in portfolio_windows.items():
        name_windows = [
            next(window for window in item.performance_windows if window.key == key)
            for item in snapshot.underlyings
        ]
        assert sum((window.option_cash for window in name_windows), D("0")) == (
            portfolio.option_cash
        )
        assert sum((window.dividends for window in name_windows), D("0")) == (portfolio.dividends)
        assert sum((window.gross_premium for window in name_windows), D("0")) == (
            portfolio.gross_premium
        )
        assert sum((window.buyback_cost for window in name_windows), D("0")) == (
            portfolio.buyback_cost
        )

    for item in snapshot.underlyings:
        quarter = next(window for window in item.performance_windows if window.key == "quarter")
        assert quarter.option_cash == item.net_option_cash
        assert quarter.dividends == item.quarter_dividends
        assert quarter.option_apr == item.quarter_option_apr
        assert quarter.total_cash_apr == item.quarter_total_cash_apr


def test_open_call_clocks_expose_per_contract_dte_and_reconcile_theta() -> None:
    snapshot = DemoDashboardReader().execute()
    clocks = [clock for item in snapshot.underlyings for clock in item.open_call_clocks]

    assert len(clocks) == 5
    assert sum(clock.contracts for clock in clocks) == snapshot.covered_calls.active_contracts
    assert sum((clock.short_theta_per_day for clock in clocks), D("0")) == (
        snapshot.risk.daily_theta
    )
    for clock in clocks:
        assert clock.days_to_expiration == (clock.expires_on - snapshot.as_of.date()).days
        assert clock.theta_per_share < D("0")
        assert clock.short_theta_per_day > D("0")
        assert clock.remaining_extrinsic_value > D("0")
        assert D("0") <= clock.time_remaining_percent <= D("100")
