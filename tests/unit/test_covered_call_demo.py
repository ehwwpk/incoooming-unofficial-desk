from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest

from schwab_dashboard.application.alerts.rolls import build_neutral_roll_scenarios
from schwab_dashboard.application.alerts.rules.dividend import evaluate_dividend_overlap
from schwab_dashboard.application.dashboard.covered_calls import RollQuoteCandidate
from schwab_dashboard.application.dashboard.performance import calculate_capital_recovery
from schwab_dashboard.application.policy.evaluate import evaluate_policy_fit
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

    assert len(snapshot.call_history) == 17
    assert len({record.record_id for record in snapshot.call_history}) == 17
    for record in snapshot.call_history:
        assert record.gross_premium == record.premium_per_share * record.contracts * 100
        assert record.net_cash == record.gross_premium - record.buyback_cost
        assert "low" not in record.sale_signal.lower()
        if record.outcome == "Open":
            assert record.closed_on is None
        else:
            assert record.closed_on is not None
            assert record.sold_on <= record.closed_on <= snapshot.as_of.date()

    policies = {
        policy.policy_id: policy
        for underlying_policy in snapshot.policies
        for policy in underlying_policy.policies
    }
    open_calls = [record for record in snapshot.call_history if record.outcome == "Open"]
    assert {(item.symbol, item.strike, item.contracts) for item in open_calls} == {
        ("CVX", D("195"), 1),
        ("CVX", D("205"), 1),
        ("CVX", D("215"), 4),
        ("KTOS", D("75"), 5),
        ("KTOS", D("90"), 3),
        ("URNM", D("67.5"), 4),
    }
    assert all(
        evaluate_policy_fit(
            policies[record.policy_id],
            strike_buffer_percent=record.strike_upside_percent,
            days_to_expiration=record.days_to_expiration,
            effective_exit_price=record.strike + record.premium_per_share,
        ).fits
        for record in open_calls
    )


def test_call_cash_and_lifecycle_reconcile_at_symbol_and_portfolio_level() -> None:
    snapshot = DemoDashboardReader().execute()
    calls = snapshot.covered_calls

    assert calls.gross_premium == D("9005.00")
    assert calls.buyback_cost == D("2665.00")
    assert calls.net_option_cash == D("6340.00")
    assert calls.open_call_credit == D("3390.00")
    assert calls.open_call_mark_value == D("1738.00")
    assert calls.open_mark_profit_loss == D("1652.00")
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
        + calls.assigned_contracts
        + calls.active_contracts
    )
    assert calls.assigned_contracts == 2
    assert calls.called_away_shares == 200
    assigned = [record for record in snapshot.call_history if record.outcome == "Assigned"]
    assert len(assigned) == 1
    assert assigned[0].symbol == "KTOS"
    assert assigned[0].contracts == 2
    assert assigned[0].underlying_at_sale == D("52.09")
    assert assigned[0].strike == D("60")
    ktos = next(item for item in snapshot.underlyings if item.symbol == "KTOS")
    assignment_day = next(
        point for point in ktos.price_points if point.date == assigned[0].closed_on
    )
    assert assignment_day.price > assigned[0].strike


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


def test_every_performance_window_reconciles_cash_and_rate_math() -> None:
    snapshot = DemoDashboardReader().execute()
    windows = {window.key: window for window in snapshot.performance_windows}

    assert tuple(windows) == ("month", "quarter", "ytd", "r365")
    for window in windows.values():
        assert window.gross_premium - window.buyback_cost == window.option_cash
        assert window.option_cash + window.dividends == window.total_cash
        expected_capture = (
            (window.option_cash / window.gross_premium * 100).quantize(D("0.1"))
            if window.gross_premium
            else D("0")
        )
        assert window.premium_capture_percent == expected_capture
        expected_drag = (
            (window.buyback_cost / window.gross_premium * 100).quantize(D("0.1"))
            if window.gross_premium
            else D("0")
        )
        assert window.buyback_drag_percent == expected_drag
        assert window.premium_capture_percent + window.buyback_drag_percent == D("100.0")

    assert windows["quarter"].option_cash == snapshot.covered_calls.net_option_cash
    assert windows["quarter"].dividends == snapshot.covered_calls.dividends
    assert windows["r365"].monthly_option_run_rate == D("2177.92")
    assert windows["r365"].monthly_total_run_rate == D("2514.00")
    assert windows["ytd"].monthly_option_run_rate == D("2269.44")


def test_monthly_performance_reconciles_to_calendar_ytd() -> None:
    snapshot = DemoDashboardReader().execute()
    ytd = next(window for window in snapshot.performance_windows if window.key == "ytd")

    assert [month.label for month in snapshot.monthly_performance] == [
        "JAN",
        "FEB",
        "MAR",
        "APR",
        "MAY",
        "JUN",
        "JUL",
        "AUG",
    ]
    assert sum((month.option_cash for month in snapshot.monthly_performance), D("0")) == (
        ytd.option_cash
    )
    assert sum((month.dividends for month in snapshot.monthly_performance), D("0")) == (
        ytd.dividends
    )
    assert all(
        month.total_cash == month.option_cash + month.dividends
        for month in snapshot.monthly_performance
    )
    assert snapshot.monthly_performance[-1].is_partial


def test_operator_metrics_report_observed_results_without_a_cash_target() -> None:
    snapshot = DemoDashboardReader().execute()
    metrics = snapshot.operator_metrics

    assert metrics.rolling_year_monthly_average == D("2177.92")
    assert metrics.rolling_three_month_average == D("2423.33")
    assert metrics.median_completed_month == D("2395")
    assert metrics.best_completed_month == D("3300")
    assert metrics.worst_completed_month == D("1700")
    assert metrics.completed_months == 7
    assert metrics.premium_capture_percent + metrics.buyback_drag_percent == D("100.0")
    assert metrics.compliant_call_tickets == 15
    assert metrics.total_call_tickets == 17
    assert metrics.uncovered_contract_capacity == (
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
        assert item.current_strike_buffer_percent > D("0")
        assert item.premium_capture_percent <= D("100")
        assert item.income_adjusted_basis_per_share < item.average_cost

    by_symbol = {item.symbol: item for item in snapshot.underlyings}
    assert by_symbol["CVX"].dividend_overlap_contracts == 5
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
    theta_by_symbol = {item.symbol: item.open_call_theta_per_day for item in snapshot.underlyings}

    assert len(clocks) == 6
    assert theta_by_symbol == {
        "CVX": D("27.00"),
        "KTOS": D("28.50"),
        "URNM": D("14.40"),
    }
    assert sum(theta_by_symbol.values(), D("0")) == snapshot.risk.daily_theta
    assert sum(clock.contracts for clock in clocks) == snapshot.covered_calls.active_contracts
    assert sum((clock.short_theta_per_day for clock in clocks), D("0")) == (
        snapshot.risk.daily_theta
    )
    for clock in clocks:
        assert clock.days_to_expiration == (clock.expires_on - snapshot.as_of.date()).days
        assert clock.original_days_to_expiration == (clock.expires_on - clock.sold_on).days
        assert clock.elapsed_days == (snapshot.as_of.date() - clock.sold_on).days
        assert clock.elapsed_days + clock.days_to_expiration == (clock.original_days_to_expiration)
        current_price = next(
            item.current_price for item in snapshot.underlyings if clock in item.open_call_clocks
        )
        assert clock.strike_distance_percent == (
            clock.strike_distance_per_share / current_price * D("100")
        ).quantize(D("0.1"))
        assert clock.elapsed_time_percent + clock.time_remaining_percent == D("100.0")
        assert clock.theta_per_share < D("0")
        assert clock.short_theta_per_day > D("0")
        assert clock.remaining_extrinsic_value > D("0")
        assert clock.entry_credit == clock.entry_credit_per_share * clock.contracts * 100
        assert clock.current_option_value == clock.mark_per_share * clock.contracts * 100
        assert clock.open_profit_loss == clock.entry_credit - clock.current_option_value
        assert clock.theta_days_of_time_value > D("0")
        assert D("0") <= clock.elapsed_time_percent <= D("100")
        assert D("0") <= clock.time_remaining_percent <= D("100")

    cvx_clock = next(
        clock
        for item in snapshot.underlyings
        if item.symbol == "CVX"
        for clock in item.open_call_clocks
        if clock.strike == D("215")
    )
    assert cvx_clock.elapsed_days == 14
    assert cvx_clock.original_days_to_expiration == 56
    assert cvx_clock.elapsed_time_percent == D("25.0")

    ktos_near = next(
        clock
        for item in snapshot.underlyings
        if item.symbol == "KTOS"
        for clock in item.open_call_clocks
        if clock.strike == D("75")
    )
    assert ktos_near.entry_credit == D("1225")
    assert ktos_near.current_option_value == D("350")
    assert ktos_near.open_profit_loss == D("875")
    assert ktos_near.option_value_vs_credit_percent == D("28.6")
    assert ktos_near.strike_distance_per_share == D("14.23")
    assert ktos_near.strike_distance_percent == D("23.4")


def test_price_paths_use_daily_closes_and_reconciled_option_events() -> None:
    snapshot = DemoDashboardReader().execute()

    for item in snapshot.underlyings:
        assert len(item.price_points) == 58
        assert item.price_points[0].x_percent == D("0.0")
        assert item.price_points[-1].x_percent == D("100.0")
        assert item.current_price == item.price_points[-1].price
        assert all(D("0") <= point.y_percent <= D("100") for point in item.price_points)
        assert sum(point.is_friday for point in item.price_points) == 11
        assert all(point.date.weekday() < 5 for point in item.price_points)
        assert tuple(point.date for point in item.price_points) == tuple(
            sorted(point.date for point in item.price_points)
        )
        assert item.thirteen_week_low <= item.current_price <= item.thirteen_week_high
        assert D("0") <= item.range_position_percent <= D("100")
        assert item.distance_from_high_percent <= D("0")
        assert {event.event_type for event in item.price_events} <= {
            "sale",
            "expired",
            "closed",
            "rolled",
            "assigned",
        }
        assert any(event.event_type == "sale" for event in item.price_events)
        assert tuple(event.sequence for event in item.price_events) == tuple(
            range(1, len(item.price_events) + 1)
        )
        lifecycle_groups: dict[int, list[object]] = {}
        for event in item.price_events:
            lifecycle_groups.setdefault(event.lifecycle_id, []).append(event)
            if event.event_type == "sale":
                assert event.linked_sale_sequence is None
                if event.outcome == "Open":
                    assert event.linked_resolution_sequence is None
                else:
                    assert event.linked_resolution_sequence is not None
            else:
                assert event.linked_sale_sequence is not None
                assert event.linked_resolution_sequence is None
            if event.outcome == "Open":
                assert event.resolved_on is None
                assert event.underlying_at_resolution is None
            else:
                assert event.resolved_on is not None
                assert event.underlying_at_resolution is not None
            if event.event_type != "sale":
                assert event.resolved_on == event.date
                assert event.underlying_at_resolution == event.price
            assert event.record_id
            assert event.campaign_id
            assert event.contracts > 0
            assert event.gross_premium > D("0")
        assert all(len(group) <= 2 for group in lifecycle_groups.values())

        prices_by_date = {point.date: point.price for point in item.price_points}
        for record in snapshot.call_history:
            if record.symbol == item.symbol:
                assert record.underlying_at_sale == prices_by_date[record.sold_on]

    by_symbol = {item.symbol: item for item in snapshot.underlyings}
    assert next(
        point.price for point in by_symbol["CVX"].price_points if point.label == "05/19"
    ) == D("197.25")
    assert next(
        point.price for point in by_symbol["KTOS"].price_points if point.label == "05/28"
    ) == D("65.19")
    assert next(
        point.price for point in by_symbol["URNM"].price_points if point.label == "06/02"
    ) == D("65.34")

    events = [event for item in snapshot.underlyings for event in item.price_events]
    assert sum(event.event_type == "sale" for event in events) == len(snapshot.call_history)
    assert sum(event.event_type != "sale" for event in events) == sum(
        record.outcome != "Open" for record in snapshot.call_history
    )
    assert all(D("0") <= event.x_percent <= D("100") for event in events)
    assert all(D("0") <= event.y_percent <= D("100") for event in events)
    for item in snapshot.underlyings:
        prices_by_date = {point.date: point.price for point in item.price_points}
        assert all(event.price == prices_by_date[event.date] for event in item.price_events)
    share_events = [event for item in snapshot.underlyings for event in item.share_trade_events]
    assert len(share_events) == 4
    assert sum(event.action == "buy" for event in share_events) == 3
    assert sum(event.action == "sell" for event in share_events) == 1
    assert all(event.glyph in {"+", "-"} for event in share_events)
    assert all(D("0") <= event.x_percent <= D("100") for event in share_events)
    assert all(D("0") <= event.y_percent <= D("100") for event in share_events)
    for item in snapshot.underlyings:
        prices_by_date = {point.date: point for point in item.price_points}
        for event in item.share_trade_events:
            anchor = prices_by_date[event.date]
            assert event.price == anchor.price
            assert event.x_percent == anchor.x_percent
            assert event.y_percent == anchor.y_percent
    assert {
        item.symbol: tuple(event.action for event in item.share_trade_events)
        for item in snapshot.underlyings
    } == {"CVX": ("buy", "sell"), "KTOS": ("buy",), "URNM": ("buy",)}
    lifecycle_pairs = {
        item.symbol: {
            (event.linked_sale_sequence, event.sequence)
            for event in item.price_events
            if event.linked_sale_sequence is not None
        }
        for item in snapshot.underlyings
    }
    assert lifecycle_pairs == {
        "CVX": {(1, 3), (2, 4), (5, 6)},
        "KTOS": {(1, 2), (3, 5), (4, 10), (6, 8)},
        "URNM": {(1, 4), (2, 6), (3, 8), (5, 7)},
    }


def test_nibwick_flags_a_near_expiration_call_without_inventing_dividend_risk() -> None:
    snapshot = DemoDashboardReader().execute()

    assert [(alert.symbol, alert.reason_code, alert.level) for alert in snapshot.alerts] == [
        ("CVX", "call_expiration_proximity", "watch")
    ]
    ktos = next(item for item in snapshot.underlyings if item.symbol == "KTOS")
    assert min(call.strike_distance_percent for call in ktos.open_call_clocks) == D("23.4")


def test_roll_checks_reject_non_later_non_higher_and_non_neutral_quotes() -> None:
    snapshot = DemoDashboardReader().execute()
    ktos = next(item for item in snapshot.underlyings if item.symbol == "KTOS")
    call = next(clock for clock in ktos.open_call_clocks if clock.strike == D("75"))
    later = call.expires_on + timedelta(days=21)
    candidates = (
        RollQuoteCandidate(later, D("70"), D("0.75"), "LOWER STRIKE"),
        RollQuoteCandidate(call.expires_on, D("80"), D("0.75"), "SAME EXPIRY"),
        RollQuoteCandidate(later, D("80"), D("1.10"), "OUTSIDE BAND"),
        RollQuoteCandidate(later, D("80"), D("0.75"), "VALID BID"),
    )

    scenarios = build_neutral_roll_scenarios(
        replace(call, roll_quote_candidates=candidates),
        current_price=ktos.current_price,
    )

    assert len(scenarios) == 1
    assert scenarios[0].quote_source == "VALID BID"
    assert scenarios[0].net_roll_per_share == D("-0.05")
    assert scenarios[0].source_option_symbol == call.record_id
    assert scenarios[0].source_expiration == call.expires_on
    assert scenarios[0].source_strike == call.strike
    assert scenarios[0].source_contracts == call.contracts


def test_dividend_warning_escalates_only_when_the_math_supports_it() -> None:
    snapshot = DemoDashboardReader().execute()
    cvx = next(item for item in snapshot.underlyings if item.symbol == "CVX")
    as_of = snapshot.as_of.date()
    at_risk_call = replace(
        cvx.open_call_clocks[0],
        contracts=3,
        strike=D("235"),
        remaining_extrinsic_value=D("300"),
    )
    at_risk = replace(
        cvx,
        current_price=D("240"),
        next_ex_dividend_date=as_of + timedelta(days=2),
        dividend_overlap_contracts=3,
        open_call_clocks=(at_risk_call,),
    )

    alert = evaluate_dividend_overlap(at_risk, as_of=as_of)

    assert alert is not None
    assert alert.level == "attention"
    assert alert.level_label == "NEEDS ATTENTION"
    assert alert.headline == "CVX's $235 call has early-assignment pressure"
    assert "through your $235 call" in alert.message
    assert "exceeds remaining time value by $0.78/share" in alert.message
    assert "classic early-assignment pressure setup" in alert.message
    assert "not a prediction" in alert.message
    assert [(fact.label, fact.value, fact.detail) for fact in alert.facts] == [
        ("EX-DIVIDEND", "AUG 09", "2 DAYS"),
        ("EXPOSED CALL", "CVX $235C", "3 CONTRACTS · 300 SHARES"),
        ("IN THE MONEY", "$5.00 / 2.1%", "STOCK $240.00"),
        ("DIV / TIME VALUE", "$1.78 / $1.00", "1.78x"),
    ]
    assert alert.method_note is not None
    assert "WITHIN FIVE CALENDAR DAYS" in alert.method_note

    check = evaluate_dividend_overlap(
        replace(at_risk, next_ex_dividend_date=as_of + timedelta(days=5)),
        as_of=as_of,
    )
    assert check is not None
    assert check.level == "check"
    assert check.headline == "CVX's $235 call has early-assignment pressure"
    assert (
        evaluate_dividend_overlap(
            replace(at_risk, next_ex_dividend_date=as_of + timedelta(days=6)), as_of=as_of
        )
        is None
    )
    assert evaluate_dividend_overlap(replace(at_risk, current_price=D("234")), as_of=as_of) is None

    time_value_rich_call = replace(at_risk_call, remaining_extrinsic_value=D("600"))
    watch = evaluate_dividend_overlap(
        replace(at_risk, open_call_clocks=(time_value_rich_call,)),
        as_of=as_of,
    )
    assert watch is not None
    assert watch.level == "watch"
    assert watch.headline == "CVX's dividend arrives before your $235 call expires"
    assert "Remaining time value is $2.00/share" in watch.message
    assert "weakens the early-exercise incentive" in watch.message
