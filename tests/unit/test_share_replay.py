from datetime import UTC, date, datetime
from decimal import Decimal

from schwab_dashboard.application.performance.baselines import build_static_share_baseline
from schwab_dashboard.application.performance.models import ReturnPoint
from schwab_dashboard.application.performance.projection import build_performance_comparison
from schwab_dashboard.application.performance.share_replay import (
    apply_discretionary_equity,
    classify_forced_equity,
    execution_keys,
    live_long_quantity,
    scaled_dividend,
)
from schwab_dashboard.application.performance.stock_leverage import stock_leverage_ratio

D = Decimal


def test_manual_buy_increases_freeze_shares_and_spends_cash() -> None:
    quantities, cash, omitted = apply_discretionary_equity(
        {"KTOS": D("100")},
        D("94000"),
        executions=(
            {
                "external_key": "buy",
                "occurred_at": datetime(2026, 8, 12, 15, tzinfo=UTC),
                "asset_type": "equity",
                "symbol": "KTOS",
                "side": "buy",
                "quantity": D("100"),
                "price": D("60"),
            },
        ),
        after=date(2026, 8, 11),
        through=date(2026, 8, 12),
        forced_keys=frozenset(),
        uncertain_symbol_days=frozenset(),
    )
    assert omitted is False
    assert quantities["KTOS"] == D("200")
    assert cash == D("88000")


def test_etf_buy_is_replayed_as_a_share_trade() -> None:
    quantities, cash, omitted = apply_discretionary_equity(
        {"SPY": D("10")},
        D("0"),
        executions=(
            {
                "external_key": "spy-buy",
                "occurred_at": datetime(2026, 8, 12, 15, tzinfo=UTC),
                "asset_type": "ETF",
                "symbol": "SPY",
                "side": "BUY",
                "quantity": D("2"),
                "net_cash": D("-1280"),
            },
        ),
        after=date(2026, 8, 11),
        through=date(2026, 8, 12),
        forced_keys=frozenset(),
        uncertain_symbol_days=frozenset(),
    )

    assert quantities == {"SPY": D("12")}
    assert cash == D("-1280")
    assert omitted is False


def test_manual_trade_uses_fee_net_broker_cash_when_available() -> None:
    quantities, cash, omitted = apply_discretionary_equity(
        {"KTOS": D("100")},
        D("94000"),
        executions=(
            {
                "external_key": "buy-with-fee",
                "occurred_at": datetime(2026, 8, 12, 15, tzinfo=UTC),
                "asset_type": "equity",
                "symbol": "KTOS",
                "side": "buy",
                "quantity": D("100"),
                "price": D("60"),
                "net_cash": D("-6010"),
            },
        ),
        after=date(2026, 8, 11),
        through=date(2026, 8, 12),
        forced_keys=frozenset(),
        uncertain_symbol_days=frozenset(),
    )

    assert omitted is False
    assert quantities["KTOS"] == D("200")
    assert cash == D("87990")


def test_manual_trade_fallback_subtracts_reported_fees() -> None:
    quantities, cash, omitted = apply_discretionary_equity(
        {"KTOS": D("100")},
        D("94000"),
        executions=(
            {
                "external_key": "buy-with-fallback-fee",
                "occurred_at": datetime(2026, 8, 12, 15, tzinfo=UTC),
                "asset_type": "AssetType.EQUITY",
                "symbol": "KTOS",
                "side": "buy",
                "quantity": D("100"),
                "price": D("60"),
                "fees": D("10"),
            },
        ),
        after=date(2026, 8, 11),
        through=date(2026, 8, 12),
        forced_keys=frozenset(),
        uncertain_symbol_days=frozenset(),
    )

    assert omitted is False
    assert quantities == {"KTOS": D("200")}
    assert cash == D("87990")


def test_unsupported_same_day_short_round_trip_is_omitted_atomically() -> None:
    occurred = datetime(2026, 8, 12, 15, tzinfo=UTC)
    quantities, cash, omitted = apply_discretionary_equity(
        {},
        D("10000"),
        executions=(
            {
                "external_key": "short-sale",
                "occurred_at": occurred,
                "asset_type": "equity",
                "symbol": "KTOS",
                "side": "sell",
                "quantity": D("100"),
                "price": D("60"),
            },
            {
                "external_key": "cover",
                "occurred_at": occurred,
                "asset_type": "equity",
                "symbol": "KTOS",
                "side": "buy",
                "quantity": D("100"),
                "price": D("59"),
            },
        ),
        after=date(2026, 8, 11),
        through=date(2026, 8, 12),
        forced_keys=frozenset(),
        uncertain_symbol_days=frozenset(),
    )

    assert omitted is True
    assert quantities == {}
    assert cash == D("10000")


def test_share_replay_ignores_another_account_when_one_is_selected() -> None:
    quantities, cash, omitted = apply_discretionary_equity(
        {"KTOS": D("100")},
        D("94000"),
        executions=(
            {
                **_equity(
                    "other-account",
                    account="account-b",
                    side="buy",
                    quantity="100",
                    price="60",
                ),
                "account_id": "account-b",
            },
        ),
        after=date(2026, 8, 11),
        through=date(2026, 8, 12),
        forced_keys=frozenset(),
        uncertain_symbol_days=frozenset(),
        account="account-a",
    )

    assert omitted is False
    assert quantities == {"KTOS": D("100")}
    assert cash == D("94000")


def test_call_assignment_equity_sell_is_forced_and_does_not_cut_freeze_shares() -> None:
    executions = (
        {
            "external_key": "called-away",
            "occurred_at": datetime(2026, 8, 12, 20, tzinfo=UTC),
            "asset_type": "equity",
            "symbol": "KTOS",
            "side": "sell",
            "quantity": D("200"),
            "price": D("65"),
        },
    )
    lifecycle = (
        {
            "event_type": "assignment",
            "option_side": "call",
            "occurred_at": datetime(2026, 8, 12, 20, tzinfo=UTC),
            "underlying_symbol": "KTOS",
            "strike": D("65"),
            "option_quantity": D("2"),
            "stock_quantity": D("200"),
        },
    )
    forced, uncertain = classify_forced_equity(
        executions=executions,
        lifecycle_events=lifecycle,
    )
    assert "called-away" in forced
    assert not uncertain
    quantities, cash, _ = apply_discretionary_equity(
        {"KTOS": D("200")},
        D("80000"),
        executions=executions,
        after=date(2026, 8, 11),
        through=date(2026, 8, 12),
        forced_keys=forced,
        uncertain_symbol_days=uncertain,
    )
    assert quantities["KTOS"] == D("200")
    assert cash == D("80000")


def test_put_assignment_equity_buy_does_not_increase_freeze_shares() -> None:
    executions = (
        {
            "external_key": "put-to",
            "occurred_at": datetime(2026, 8, 12, 20, tzinfo=UTC),
            "asset_type": "equity",
            "symbol": "KTOS",
            "side": "buy",
            "quantity": D("100"),
            "price": D("60"),
        },
    )
    lifecycle = (
        {
            "event_type": "assignment",
            "option_side": "put",
            "occurred_at": datetime(2026, 8, 12, 20, tzinfo=UTC),
            "underlying_symbol": "KTOS",
            "strike": D("60"),
            "option_quantity": D("1"),
            "stock_quantity": D("100"),
        },
    )
    forced, _uncertain = classify_forced_equity(
        executions=executions,
        lifecycle_events=lifecycle,
    )
    quantities, cash, _ = apply_discretionary_equity(
        {"KTOS": D("100")},
        D("94000"),
        executions=executions,
        after=date(2026, 8, 11),
        through=date(2026, 8, 12),
        forced_keys=forced,
        uncertain_symbol_days=frozenset(),
    )
    assert quantities["KTOS"] == D("100")
    assert cash == D("94000")


def test_sqlite_date_only_assignment_keeps_its_stated_market_date() -> None:
    executions = (
        {
            "external_key": "put-delivery",
            "occurred_at": datetime(2026, 8, 12, 15, tzinfo=UTC),
            "asset_type": "equity",
            "symbol": "KTOS",
            "side": "buy",
            "quantity": D("100"),
            "price": D("60"),
        },
    )
    lifecycle = (
        {
            "event_type": "assigned",
            "option_side": "put",
            # SQLite returns Schwab's date-only midnight without its ET offset.
            "occurred_at": datetime(2026, 8, 12),
            "underlying_symbol": "KTOS",
            "strike": D("60"),
            "option_quantity": D("1"),
            "stock_quantity": D("100"),
        },
    )

    forced, uncertain = classify_forced_equity(
        executions=executions,
        lifecycle_events=lifecycle,
    )

    assert forced == frozenset({"put-delivery"})
    assert not uncertain


def test_duplicate_unkeyed_fills_have_stable_occurrence_keys_and_match_as_one_delivery() -> None:
    executions = (
        _equity(None, account="...1234", side="buy", quantity="100", price="60"),
        _equity(None, account="...1234", side="buy", quantity="100", price="60"),
    )
    copied = tuple(dict(row) for row in executions)
    first_keys = tuple(key for key, _row in execution_keys(executions))
    copied_keys = tuple(key for key, _row in execution_keys(copied))

    assert first_keys == copied_keys
    assert first_keys[0] != first_keys[1]
    assert first_keys[0].endswith(":1")
    assert first_keys[1].endswith(":2")

    forced, uncertain = classify_forced_equity(
        executions=executions,
        lifecycle_events=(
            _lifecycle(
                "assigned",
                account="...1234",
                option_side="PUT",
                stock_quantity="200",
            ),
        ),
    )
    assert forced == frozenset(first_keys)
    assert not uncertain

    quantities, cash, omitted = apply_discretionary_equity(
        {"KTOS": D("100")},
        D("94000"),
        executions=copied,
        after=date(2026, 8, 11),
        through=date(2026, 8, 12),
        forced_keys=forced,
        uncertain_symbol_days=uncertain,
    )
    assert quantities == {"KTOS": D("100")}
    assert cash == D("94000")
    assert omitted is False


def test_expiration_does_not_turn_an_equity_trade_into_forced_delivery() -> None:
    executions = (_equity("manual-sale", side="sell", quantity="100", price="60"),)
    forced, uncertain = classify_forced_equity(
        executions=executions,
        lifecycle_events=(
            _lifecycle(
                "expiration",
                option_side="call",
                stock_quantity="100",
            ),
        ),
    )
    assert not forced
    assert not uncertain

    quantities, cash, omitted = apply_discretionary_equity(
        {"KTOS": D("200")},
        D("88000"),
        executions=executions,
        after=date(2026, 8, 11),
        through=date(2026, 8, 12),
        forced_keys=forced,
        uncertain_symbol_days=uncertain,
    )
    assert quantities == {"KTOS": D("100")}
    assert cash == D("94000")
    assert omitted is False


def test_exercise_aliases_use_the_opposite_delivery_directions_from_assignment() -> None:
    executions = (
        _equity("call-exercise", side="BUY", quantity="100", price="60"),
        _equity("put-exercise", symbol="CVX", side="SELL", quantity="100", price="195"),
    )
    lifecycle = (
        _lifecycle("Exercised", option_side="CALL", stock_quantity="100"),
        _lifecycle(
            "EXERCISE",
            symbol="CVX",
            option_side="Put",
            strike="195",
            stock_quantity="100",
        ),
    )

    forced, uncertain = classify_forced_equity(
        executions=executions,
        lifecycle_events=lifecycle,
    )

    assert forced == frozenset({"call-exercise", "put-exercise"})
    assert not uncertain


def test_forced_delivery_matching_is_isolated_by_account() -> None:
    executions = (
        _equity("forced", account="...1111", side="buy", quantity="100", price="60"),
        _equity("manual", account="...2222", side="buy", quantity="100", price="60"),
    )
    forced, uncertain = classify_forced_equity(
        executions=executions,
        lifecycle_events=(
            _lifecycle(
                "assignment",
                account="...1111",
                option_side="put",
                stock_quantity="100",
            ),
        ),
    )
    assert forced == frozenset({"forced"})
    assert not uncertain

    quantities, cash, omitted = apply_discretionary_equity(
        {"KTOS": D("100")},
        D("94000"),
        executions=executions,
        after=date(2026, 8, 11),
        through=date(2026, 8, 12),
        forced_keys=forced,
        uncertain_symbol_days=uncertain,
    )
    assert quantities == {"KTOS": D("200")}
    assert cash == D("88000")
    assert omitted is False


def test_split_delivery_uses_the_only_quantity_subset() -> None:
    executions = (
        _equity("split-40", side="buy", quantity="40", price="60"),
        _equity("split-60", side="buy", quantity="60", price="60"),
        _equity("manual-25", side="buy", quantity="25", price="60"),
    )
    forced, uncertain = classify_forced_equity(
        executions=executions,
        lifecycle_events=(_lifecycle("assigned", option_side="put", stock_quantity="100"),),
    )

    assert forced == frozenset({"split-40", "split-60"})
    assert not uncertain


def test_ambiguous_quantity_subsets_omit_the_account_symbol_day() -> None:
    executions = (
        _equity("whole", side="buy", quantity="200", price="60"),
        _equity("half-1", side="buy", quantity="100", price="60"),
        _equity("half-2", side="buy", quantity="100", price="60"),
    )
    forced, uncertain = classify_forced_equity(
        executions=executions,
        lifecycle_events=(_lifecycle("assignment", option_side="put", stock_quantity="200"),),
    )
    assert not forced
    assert uncertain == frozenset({("", "KTOS", date(2026, 8, 12))})

    quantities, cash, omitted = apply_discretionary_equity(
        {"KTOS": D("100")},
        D("94000"),
        executions=executions,
        after=date(2026, 8, 11),
        through=date(2026, 8, 12),
        forced_keys=forced,
        uncertain_symbol_days=uncertain,
    )
    assert quantities == {"KTOS": D("100")}
    assert cash == D("94000")
    assert omitted is True


def test_stock_leverage_ignores_maintenance_and_uses_stock_ex_overlay_capital() -> None:
    row = {
        "liquidation_value": D("100000"),
        "long_market_value": D("80000"),
        "long_option_market_value": D("0"),
        "short_option_market_value": D("-2000"),
        "maintenance_requirement": D("999999"),
    }
    twin = dict(row)
    twin["maintenance_requirement"] = D("0")
    assert stock_leverage_ratio(row) == D("80000") / D("102000")
    assert stock_leverage_ratio(row) == stock_leverage_ratio(twin)


def test_dividend_scales_to_freeze_lots() -> None:
    credited = scaled_dividend(
        {"amount": D("100")},
        freeze_qty=D("1000"),
        live_qty=D("800"),
    )
    assert credited == D("125")


def test_live_long_quantity_uses_latest_snapshot_per_account_not_every_sync() -> None:
    history = (
        _lot("KTOS", "1000", "2026-08-24T14:00:00+00:00"),
        _lot("KTOS", "1100", "2026-08-24T20:00:00+00:00"),
        {
            **_lot("KTOS", "200", "2026-08-24T19:00:00+00:00"),
            "account_mask": "...5678",
            "sync_run_id": "run-second-account",
        },
    )

    assert live_long_quantity(history, "KTOS", date(2026, 8, 24)) == D("1300")


def test_live_long_quantity_reads_absence_from_later_snapshot_as_zero() -> None:
    history = (
        _lot("KTOS", "1000", "2026-08-21T20:00:00+00:00"),
        _lot("CVX", "800", "2026-08-24T20:00:00+00:00"),
    )

    assert live_long_quantity(history, "KTOS", date(2026, 8, 24)) == D("0")


def test_option_premium_does_not_enter_freeze_nav() -> None:
    comparison = build_performance_comparison(
        balance_history=(
            _balance("2026-08-11T20:00:00+00:00", "100000"),
            _balance("2026-08-12T20:00:00+00:00", "101000"),
        ),
        cash_movements=(),
        position_history=(_lot("KTOS", "100", "2026-08-11T20:00:00+00:00"),),
        daily_bars=(
            {"symbol": "KTOS", "trade_date": date(2026, 8, 11), "close": D("60")},
            {"symbol": "KTOS", "trade_date": date(2026, 8, 12), "close": D("63")},
        ),
        executions=(
            {
                "external_key": "put",
                "occurred_at": datetime(2026, 8, 12, 15, tzinfo=UTC),
                "asset_type": "option",
                "side": "sell",
                "position_effect": "opening",
                "option_side": "put",
                "net_cash": D("5000"),
            },
        ),
    )
    freeze = comparison.shares_without_options
    assert freeze.return_percent == D("0.3")
    assert freeze.points[-1].value == D("100300")
    assert comparison.option_overlay.return_percent == D("5")
    assert comparison.methodology_version == "incoooming-performance-v11"


def test_scaled_dividend_hits_freeze_nav() -> None:
    points = (
        ReturnPoint(
            date=date(2026, 8, 11),
            value=D("100000"),
            external_flow=D("0"),
            daily_return_percent=None,
            cumulative_return_percent=None,
            quality="observed",
        ),
        ReturnPoint(
            date=date(2026, 8, 12),
            value=D("100000"),
            external_flow=D("0"),
            daily_return_percent=D("0"),
            cumulative_return_percent=D("0"),
            quality="observed",
        ),
    )
    series = build_static_share_baseline(
        position_history=(
            {
                "sync_run_id": "run-1",
                "observed_at": datetime(2026, 8, 11, 20, tzinfo=UTC),
                "symbol": "KTOS",
                "asset_type": "EQUITY",
                "net_quantity": D("1000"),
            },
            {
                "sync_run_id": "run-2",
                "observed_at": datetime(2026, 8, 12, 20, tzinfo=UTC),
                "symbol": "KTOS",
                "asset_type": "EQUITY",
                "net_quantity": D("800"),
            },
        ),
        daily_bars=(
            {"symbol": "KTOS", "trade_date": date(2026, 8, 11), "close": D("60")},
            {"symbol": "KTOS", "trade_date": date(2026, 8, 12), "close": D("60")},
        ),
        cash_movements=(
            {
                "occurred_at": datetime(2026, 8, 12, 12, tzinfo=UTC),
                "movement_type": "dividend",
                "symbol": "KTOS",
                "amount": D("100"),
            },
        ),
        actual_points=points,
    )
    assert series.points[-1].value - series.points[0].value == D("125")


def test_static_baseline_uses_managed_sessions_and_keeps_intervening_dividends() -> None:
    points = (
        ReturnPoint(
            date=date(2026, 8, 11),
            value=D("100000"),
            external_flow=D("0"),
            daily_return_percent=None,
            cumulative_return_percent=None,
            quality="observed",
        ),
        ReturnPoint(
            date=date(2026, 8, 13),
            value=D("100100"),
            external_flow=D("0"),
            daily_return_percent=D("0.1"),
            cumulative_return_percent=D("0.1"),
            quality="observed",
        ),
    )
    series = build_static_share_baseline(
        position_history=(_lot("KTOS", "100", "2026-08-11T20:00:00+00:00"),),
        daily_bars=(
            {"symbol": "KTOS", "trade_date": date(2026, 8, 11), "close": D("60")},
            {"symbol": "KTOS", "trade_date": date(2026, 8, 13), "close": D("60")},
            # This unrelated row used to create a fake Aug 12 portfolio point.
            {"symbol": "UNRELATED", "trade_date": date(2026, 8, 12), "close": D("10")},
        ),
        cash_movements=(
            {
                "occurred_at": datetime(2026, 8, 12, 12, tzinfo=UTC),
                "movement_type": "dividend",
                "symbol": "KTOS",
                "amount": D("25"),
            },
        ),
        actual_points=points,
    )

    assert [point.date for point in series.points] == [date(2026, 8, 11), date(2026, 8, 13)]
    assert series.points[-1].value - series.points[0].value == D("25")


def test_static_baseline_never_converts_a_missing_close_to_zero() -> None:
    points = (
        ReturnPoint(
            date=date(2026, 8, 11),
            value=D("100000"),
            external_flow=D("0"),
            daily_return_percent=None,
            cumulative_return_percent=None,
            quality="observed",
        ),
        ReturnPoint(
            date=date(2026, 8, 12),
            value=D("100000"),
            external_flow=D("0"),
            daily_return_percent=D("0"),
            cumulative_return_percent=D("0"),
            quality="observed",
        ),
    )

    series = build_static_share_baseline(
        position_history=(_lot("KTOS", "100", "2026-08-11T20:00:00+00:00"),),
        daily_bars=(
            {"symbol": "KTOS", "trade_date": date(2026, 8, 11), "close": D("60")},
            {"symbol": "KTOS", "trade_date": date(2026, 8, 12), "close": None},
        ),
        cash_movements=(),
        actual_points=points,
    )

    assert len(series.points) == 2
    assert tuple(point.value for point in series.points) == (D("100000"), D("100000"))
    assert series.status == "carried_forward"
    assert series.return_percent == D("0")


def test_static_baseline_keeps_non_equity_positions_in_the_frozen_residual() -> None:
    points = (
        ReturnPoint(
            date=date(2026, 8, 11),
            value=D("100000"),
            external_flow=D("0"),
            daily_return_percent=None,
            cumulative_return_percent=None,
            quality="observed",
        ),
        ReturnPoint(
            date=date(2026, 8, 12),
            value=D("100100"),
            external_flow=D("0"),
            daily_return_percent=D("0.1"),
            cumulative_return_percent=D("0.1"),
            quality="observed",
        ),
    )
    fixed_income = {
        **_lot("US-TREASURY", "10", "2026-08-11T20:00:00+00:00"),
        "asset_type": "FIXED_INCOME",
    }

    series = build_static_share_baseline(
        position_history=(
            _lot("KTOS", "100", "2026-08-11T20:00:00+00:00"),
            fixed_income,
        ),
        daily_bars=(
            {"symbol": "KTOS", "trade_date": date(2026, 8, 11), "close": D("60")},
            {"symbol": "KTOS", "trade_date": date(2026, 8, 12), "close": D("61")},
        ),
        cash_movements=(),
        actual_points=points,
    )

    assert series.status == "derived"
    assert series.points[0].value == D("100000")
    assert series.points[1].value == D("100100")
    assert series.return_percent == D("0.1")


def test_static_baseline_keeps_opening_residual_and_excludes_assigned_put_delivery() -> None:
    points = (
        ReturnPoint(
            date=date(2026, 8, 11),
            value=D("100000"),
            external_flow=D("0"),
            daily_return_percent=None,
            cumulative_return_percent=None,
            quality="observed",
        ),
        ReturnPoint(
            date=date(2026, 8, 12),
            value=D("50000"),
            external_flow=D("0"),
            daily_return_percent=D("-50"),
            cumulative_return_percent=D("-50"),
            quality="observed",
        ),
    )
    series = build_static_share_baseline(
        position_history=(_lot("KTOS", "100", "2026-08-11T20:00:00+00:00"),),
        daily_bars=(
            {"symbol": "KTOS", "trade_date": date(2026, 8, 11), "close": D("60")},
            {"symbol": "KTOS", "trade_date": date(2026, 8, 12), "close": D("50")},
        ),
        cash_movements=(),
        actual_points=points,
        executions=(_equity("assigned-put", side="buy", quantity="100", price="60"),),
        lifecycle_events=(_lifecycle("assigned", option_side="PUT", stock_quantity="100"),),
    )

    assert series.points[0].value == D("100000")
    assert series.points[-1].value == D("99000")
    assert series.return_percent == D("-1")


def test_static_baseline_uses_latest_same_day_position_snapshot_regardless_of_input_order() -> None:
    points = (
        ReturnPoint(
            date=date(2026, 8, 11),
            value=D("100000"),
            external_flow=D("0"),
            daily_return_percent=None,
            cumulative_return_percent=None,
            quality="observed",
        ),
        ReturnPoint(
            date=date(2026, 8, 12),
            value=D("100000"),
            external_flow=D("0"),
            daily_return_percent=D("0"),
            cumulative_return_percent=D("0"),
            quality="observed",
        ),
    )
    later = {
        **_lot("KTOS", "100", "2026-08-11T20:00:00+00:00"),
        "sync_run_id": "run-later",
    }
    earlier = {
        **_lot("KTOS", "200", "2026-08-11T18:00:00+00:00"),
        "sync_run_id": "run-earlier",
    }

    series = build_static_share_baseline(
        position_history=(later, earlier),
        daily_bars=(
            {"symbol": "KTOS", "trade_date": date(2026, 8, 11), "close": D("60")},
            {"symbol": "KTOS", "trade_date": date(2026, 8, 12), "close": D("61")},
        ),
        cash_movements=(),
        actual_points=points,
    )

    assert series.points[-1].value == D("100100")
    assert series.return_percent == D("0.1")


def test_opening_day_dividend_is_not_added_twice_to_the_frozen_residual() -> None:
    points = (
        ReturnPoint(
            date=date(2026, 8, 11),
            value=D("100000"),
            external_flow=D("0"),
            daily_return_percent=None,
            cumulative_return_percent=None,
            quality="observed",
        ),
        ReturnPoint(
            date=date(2026, 8, 12),
            value=D("100000"),
            external_flow=D("0"),
            daily_return_percent=D("0"),
            cumulative_return_percent=D("0"),
            quality="observed",
        ),
    )
    series = build_static_share_baseline(
        position_history=(_lot("KTOS", "100", "2026-08-11T20:00:00+00:00"),),
        daily_bars=(
            {"symbol": "KTOS", "trade_date": date(2026, 8, 11), "close": D("60")},
            {"symbol": "KTOS", "trade_date": date(2026, 8, 12), "close": D("60")},
        ),
        cash_movements=(
            {
                "occurred_at": datetime(2026, 8, 11, 12, tzinfo=UTC),
                "movement_type": "dividend",
                "symbol": "KTOS",
                "amount": D("100"),
            },
        ),
        actual_points=points,
    )

    assert tuple(point.value for point in series.points) == (D("100000"), D("100000"))


def _lot(symbol: str, quantity: str, observed: str) -> dict[str, object]:
    return {
        "sync_run_id": "run-1",
        "account_mask": "...1234",
        "observed_at": datetime.fromisoformat(observed),
        "symbol": symbol,
        "asset_type": "EQUITY",
        "net_quantity": D(quantity),
    }


def _balance(observed: str, liquidation: str) -> dict[str, object]:
    return {
        "account_mask": "...1234",
        "observed_at": datetime.fromisoformat(observed),
        "liquidation_value": D(liquidation),
        "initial_liquidation_value": D(liquidation),
    }


def _equity(
    key: str | None,
    *,
    account: str = "",
    symbol: str = "KTOS",
    side: str,
    quantity: str,
    price: str,
) -> dict[str, object]:
    return {
        "external_key": key,
        "account_mask": account,
        "occurred_at": datetime(2026, 8, 12, 20, tzinfo=UTC),
        "asset_type": "equity",
        "symbol": symbol,
        "side": side,
        "quantity": D(quantity),
        "price": D(price),
    }


def _lifecycle(
    event_type: str,
    *,
    account: str = "",
    symbol: str = "KTOS",
    option_side: str,
    strike: str = "60",
    stock_quantity: str,
) -> dict[str, object]:
    return {
        "event_type": event_type,
        "account_mask": account,
        "option_side": option_side,
        "occurred_at": datetime(2026, 8, 12, 20, tzinfo=UTC),
        "underlying_symbol": symbol,
        "strike": D(strike),
        "option_quantity": D("1"),
        "stock_quantity": D(stock_quantity),
    }
