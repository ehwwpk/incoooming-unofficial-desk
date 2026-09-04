from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from schwab_dashboard.application.dashboard.calculations import account_day_profit_loss
from schwab_dashboard.application.performance.projection import build_performance_comparison
from schwab_dashboard.application.performance.reconstruction import (
    _activity_timestamp,
    _anchor_marks,
    _execution_marks,
    _Holding,
    _holdings,
    _mark_on,
    build_reconstructed_balance_history,
)
from schwab_dashboard.application.performance.returns import (
    _aggregate_price_coverage,
    _aggregate_raw_value,
    build_time_weighted_returns,
)
from schwab_dashboard.application.performance.risk import calculate_risk_statistics
from schwab_dashboard.application.performance.sessions import build_market_calendar

D = Decimal


def test_incomplete_account_reconstruction_metadata_is_not_partially_aggregated() -> None:
    rows = (
        {
            "synthetic": True,
            "price_coverage_percent": D("100"),
            "raw_reconstructed_value": D("100"),
        },
        {
            "synthetic": True,
            "price_coverage_percent": None,
            "raw_reconstructed_value": None,
        },
    )

    assert _aggregate_price_coverage(rows) is None
    assert _aggregate_raw_value(rows) is None


def test_mixed_observed_and_reconstructed_raw_value_includes_every_account() -> None:
    rows = (
        {"synthetic": False, "liquidation_value": D("200")},
        {
            "synthetic": True,
            "price_coverage_percent": D("95"),
            "raw_reconstructed_value": D("100"),
        },
    )

    assert _aggregate_price_coverage(rows) == D("95")
    assert _aggregate_raw_value(rows) == D("300")


def test_same_timestamp_execution_mark_is_a_deterministic_quantity_weighted_price() -> None:
    occurred = datetime.fromisoformat("2026-09-01T14:48:20-04:00")
    rows = (
        {
            "symbol": "CVX  260918C00215000",
            "occurred_at": occurred,
            "quantity": D("1"),
            "price": D("3"),
        },
        {
            "symbol": "CVX260918C00215000",
            "occurred_at": occurred,
            "quantity": D("2"),
            "price": D("4.5"),
        },
    )

    assert _execution_marks(rows) == {"CVX260918C00215000": ((date(2026, 9, 1), D("4")),)}


def test_zero_execution_mark_is_valid_only_for_an_option() -> None:
    occurred = datetime.fromisoformat("2026-09-01T14:48:20-04:00")

    assert _execution_marks(
        (
            {
                "symbol": "KTOS",
                "asset_type": "equity",
                "occurred_at": occurred,
                "quantity": D("1"),
                "price": D("0"),
            },
            {
                "symbol": "KTOS  260918C00075000",
                "asset_type": "option",
                "occurred_at": occurred,
                "quantity": D("1"),
                "price": D("0"),
            },
        )
    ) == {"KTOS260918C00075000": ((date(2026, 9, 1), D("0")),)}


def test_zero_equity_anchor_is_not_an_estimated_mark_source() -> None:
    assert (
        _anchor_marks(
            (
                {
                    "symbol": "KTOS",
                    "asset_type": "equity",
                    "net_quantity": D("100"),
                    "market_value": D("0"),
                },
            ),
            (),
            date(2026, 8, 31),
            date(2026, 9, 1),
        )
        == {}
    )


def test_post_expiration_option_bar_cannot_resurrect_a_contract() -> None:
    day = date(2026, 9, 1)
    bars = {
        ("KTOS260828C00075000", day): D("9"),
        ("KTOS", day): D("80"),
    }
    holding = _Holding(
        symbol="KTOS260828C00075000",
        asset_type="option",
        quantity=D("-1"),
        multiplier=D("100"),
        market_value=None,
        underlying_symbol="KTOS",
        option_side="call",
        expiration_date=date(2026, 8, 28),
        strike=D("75"),
        is_non_standard=False,
    )

    assert _mark_on(
        holding,
        day=day,
        bars=bars,
        anchor_marks={},
        calendar=build_market_calendar(({"symbol": "SPY", "trade_date": day, "close": D("100")},)),
    ) == (D("0"), False)


def test_duplicate_compatible_snapshot_rows_are_summed_not_overwritten() -> None:
    rows = (
        {
            "symbol": "KTOS",
            "asset_type": "equity",
            "net_quantity": D("40"),
            "market_value": D("2000"),
        },
        {
            "symbol": " ktos ",
            "asset_type": "ETF",
            "net_quantity": D("60"),
            "market_value": D("3000"),
        },
    )

    holdings, unambiguous = _holdings(rows)

    assert unambiguous is True
    assert holdings["KTOS"].quantity == D("100")
    assert holdings["KTOS"].market_value == D("5000")


def test_gap_is_replayed_between_observed_anchors_and_right_return_inherits_quality() -> None:
    comparison = build_performance_comparison(
        balance_history=(
            _balance("a", "...1234", "run-left", "2026-08-27T20:30:00+00:00", "100000"),
            _balance("a", "...1234", "run-right", "2026-09-03T20:30:00+00:00", "101000"),
        ),
        position_history=(
            _position("a", "run-left", "2026-08-27T20:30:00+00:00", "5000"),
            _position("a", "run-right", "2026-09-03T20:30:00+00:00", "6000"),
        ),
        cash_movements=(),
        daily_bars=tuple(
            {"symbol": symbol, "trade_date": day, "close": close}
            for symbol, closes in {
                "SPY": (
                    ("2026-08-27", "100"),
                    ("2026-08-28", "100"),
                    ("2026-08-31", "100"),
                    ("2026-09-01", "100"),
                    ("2026-09-02", "100"),
                    ("2026-09-03", "100"),
                ),
                "KTOS": (
                    ("2026-08-27", "50"),
                    ("2026-08-28", "51"),
                    ("2026-08-31", "52"),
                    ("2026-09-01", "53"),
                    ("2026-09-02", "55"),
                    ("2026-09-03", "60"),
                ),
            }.items()
            for raw_day, raw_close in closes
            for day, close in ((date.fromisoformat(raw_day), D(raw_close)),)
        ),
    )

    points = comparison.actual.points
    assert [point.date for point in points] == [
        date(2026, 8, 27),
        date(2026, 8, 28),
        date(2026, 8, 31),
        date(2026, 9, 1),
        date(2026, 9, 2),
        date(2026, 9, 3),
    ]
    assert [point.value_quality for point in points[1:-1]] == ["derived"] * 4
    assert points[-1].value_quality == "observed"
    assert points[-1].return_quality == "derived"
    assert comparison.reconstructed_sessions == 4
    assert comparison.estimated_sessions == 0
    assert account_day_profit_loss(points).status == "derived"


def test_unreconstructed_gap_is_an_interval_change_not_a_daily_return() -> None:
    bars = tuple(
        {"symbol": "SPY", "trade_date": date.fromisoformat(day), "close": D("100")}
        for day in ("2026-08-27", "2026-08-28", "2026-08-31", "2026-09-01")
    )
    calendar = build_market_calendar(bars)
    points = build_time_weighted_returns(
        (
            _balance("a", "...1234", "left", "2026-08-27T20:30:00+00:00", "100000"),
            _balance("a", "...1234", "right", "2026-09-01T20:30:00+00:00", "99000"),
        ),
        (),
        calendar=calendar,
    )

    assert points[-1].session_span == 3
    assert points[-1].daily_return_percent is None
    assert points[-1].interval_return_percent == D("-1")
    assert points[-1].return_quality == "multi_session"
    change = account_day_profit_loss(points)
    assert change.status == "multi_session"
    assert change.profit_loss == D("-1000")
    assert calculate_risk_statistics(points).observations == 0


def test_same_visible_mask_does_not_merge_distinct_accounts() -> None:
    calendar = build_market_calendar(
        (
            {"symbol": "SPY", "trade_date": date(2026, 8, 11), "close": D("100")},
            {"symbol": "SPY", "trade_date": date(2026, 8, 12), "close": D("100")},
        )
    )
    points = build_time_weighted_returns(
        (
            _balance("account-a", "...1234", "one", "2026-08-11T20:30:00+00:00", "100"),
            _balance("account-b", "...1234", "one", "2026-08-11T20:30:00+00:00", "200"),
            _balance("account-a", "...1234", "two", "2026-08-12T20:30:00+00:00", "110"),
            _balance("account-b", "...1234", "two", "2026-08-12T20:30:00+00:00", "220"),
        ),
        (),
        calendar=calendar,
    )

    assert points[0].value == D("300")
    assert points[1].value == D("330")
    assert points[1].daily_return_percent == D("10")


def test_nonstandard_option_uses_labelled_endpoint_bridge() -> None:
    comparison = build_performance_comparison(
        balance_history=(
            _balance("a", "...1234", "left", "2026-08-27T20:30:00+00:00", "100000"),
            _balance("a", "...1234", "right", "2026-09-01T20:30:00+00:00", "103000"),
        ),
        position_history=(
            {
                **_position("a", "left", "2026-08-27T20:30:00+00:00", "-500"),
                "symbol": "XYZ1  260918C00050000",
                "asset_type": "OPTION",
                "net_quantity": D("-1"),
                "contract_multiplier": D("50"),
                "is_non_standard": True,
                "option_type": "CALL",
                "strike": D("50"),
            },
            _position("a", "left", "2026-08-27T20:30:00+00:00", "5000"),
        ),
        cash_movements=(),
        daily_bars=tuple(
            {"symbol": symbol, "trade_date": date.fromisoformat(day), "close": D("100")}
            for symbol in ("SPY", "KTOS")
            for day in ("2026-08-27", "2026-08-28", "2026-08-31", "2026-09-01")
        ),
    )

    bridged = comparison.actual.points[1:-1]
    assert bridged
    assert all(point.value_quality == "estimated" for point in bridged)
    assert all(point.valuation_subtype == "endpoint_bridge" for point in bridged)
    assert comparison.spine.risk.observations == 0
    assert comparison.matched.quality == "estimated"
    assert comparison.spine.management_edge.status == "estimated"


def test_endpoint_bridge_applies_owner_transfer_without_inventing_return() -> None:
    comparison = build_performance_comparison(
        balance_history=(
            _balance("a", "...1234", "left", "2026-08-27T20:30:00+00:00", "100"),
            _balance("a", "...1234", "right", "2026-08-31T20:30:00+00:00", "150"),
        ),
        position_history=(
            {
                **_position("a", "left", "2026-08-27T20:30:00+00:00", "0"),
                "symbol": "XYZ1  260918C00050000",
                "asset_type": "OPTION",
                "net_quantity": D("-1"),
                "contract_multiplier": D("50"),
                "is_non_standard": True,
            },
        ),
        cash_movements=(
            {
                "account_id": "a",
                "movement_type": "transfer",
                "occurred_at": datetime.fromisoformat("2026-08-28T12:00:00-04:00"),
                "amount": D("50"),
            },
        ),
        daily_bars=tuple(
            {"symbol": "SPY", "trade_date": date.fromisoformat(day), "close": D("100")}
            for day in ("2026-08-27", "2026-08-28", "2026-08-31")
        ),
    )

    assert comparison.actual.points[1].value == D("150")
    assert comparison.actual.points[1].external_flow == D("50")
    assert comparison.actual.points[1].daily_return_percent == D("0")
    assert comparison.actual.points[2].daily_return_percent == D("0")
    assert comparison.actual.return_percent == D("0")


def test_ambiguous_assignment_fill_forces_the_whole_gap_to_endpoint_bridge() -> None:
    comparison = build_performance_comparison(
        balance_history=(
            _balance("a", "...1234", "left", "2026-08-27T20:30:00+00:00", "10000"),
            _balance("a", "...1234", "right", "2026-08-31T20:30:00+00:00", "10000"),
        ),
        position_history=(_position("a", "left", "2026-08-27T20:30:00+00:00", "5000"),),
        executions=tuple(
            {
                "external_key": f"candidate-{index}",
                "account_id": "a",
                "occurred_at": datetime.fromisoformat("2026-08-28T15:00:00-04:00"),
                "asset_type": "EQUITY",
                "symbol": "KTOS",
                "side": "BUY",
                "quantity": D("100"),
                "price": D("50"),
                "net_cash": D("-5000"),
            }
            for index in range(2)
        ),
        lifecycle_events=(
            {
                "external_key": "put-assignment",
                "account_id": "a",
                "occurred_at": datetime.fromisoformat("2026-08-28T15:00:00-04:00"),
                "event_type": "assignment",
                "option_side": "put",
                "underlying_symbol": "KTOS",
                "strike": D("50"),
                "option_quantity": D("1"),
                "stock_quantity": D("100"),
            },
        ),
        cash_movements=(),
        daily_bars=tuple(
            {"symbol": symbol, "trade_date": date.fromisoformat(day), "close": D("50")}
            for symbol in ("SPY", "KTOS")
            for day in ("2026-08-27", "2026-08-28", "2026-08-31")
        ),
    )

    assert comparison.actual.points[1].valuation_subtype == "endpoint_bridge"


def test_assignment_without_any_delivery_quantity_forces_endpoint_bridge() -> None:
    comparison = build_performance_comparison(
        balance_history=(
            _balance("a", "...1234", "left", "2026-08-27T20:30:00+00:00", "10000"),
            _balance("a", "...1234", "right", "2026-08-31T20:30:00+00:00", "10000"),
        ),
        position_history=(
            _position("a", "left", "2026-08-27T20:30:00+00:00", "5000"),
            _position("a", "right", "2026-08-31T20:30:00+00:00", "5000"),
        ),
        lifecycle_events=(
            {
                "external_key": "incomplete-assignment",
                "account_id": "a",
                "occurred_at": datetime.fromisoformat("2026-08-28T15:00:00-04:00"),
                "event_type": "assigned",
                "option_side": "put",
                "underlying_symbol": "KTOS",
                "strike": D("50"),
            },
        ),
        cash_movements=(),
        daily_bars=tuple(
            {"symbol": symbol, "trade_date": date.fromisoformat(day), "close": D("50")}
            for symbol in ("SPY", "KTOS")
            for day in ("2026-08-27", "2026-08-28", "2026-08-31")
        ),
    )

    assert comparison.actual.points[1].valuation_subtype == "endpoint_bridge"


def test_matched_assignment_execution_is_the_one_authoritative_cash_and_share_leg() -> None:
    option = {
        **_position("a", "left", "2026-08-27T20:30:00+00:00", "0"),
        "symbol": "KTOS  260918P00050000",
        "asset_type": "OPTION",
        "net_quantity": D("-1"),
        "contract_multiplier": D("100"),
        "is_non_standard": False,
        "option_type": "PUT",
        "underlying_symbol": "KTOS",
        "strike": D("50"),
    }
    assignment = {
        "external_key": "put-assignment",
        "account_id": "a",
        "occurred_at": datetime.fromisoformat("2026-08-28T15:00:00-04:00"),
        "event_type": "assignment",
        "symbol": option["symbol"],
        "option_side": "put",
        "underlying_symbol": "KTOS",
        "strike": D("50"),
        "option_quantity": D("1"),
        "stock_quantity": D("100"),
        "cash_amount": D("-5000"),
    }
    execution = {
        "external_key": "delivered-shares",
        "account_id": "a",
        "occurred_at": datetime.fromisoformat("2026-08-28T15:00:00-04:00"),
        "asset_type": "EQUITY",
        "symbol": "KTOS",
        "side": "BUY",
        "quantity": D("100"),
        "price": D("50"),
        "net_cash": D("-5000"),
    }
    comparison = build_performance_comparison(
        balance_history=(
            _balance("a", "...1234", "left", "2026-08-27T20:30:00+00:00", "10000"),
            _balance("a", "...1234", "right", "2026-08-31T20:30:00+00:00", "10000"),
        ),
        position_history=(
            option,
            _position("a", "right", "2026-08-31T20:30:00+00:00", "5000"),
        ),
        executions=(execution,),
        lifecycle_events=(assignment,),
        cash_movements=(),
        daily_bars=tuple(
            {"symbol": symbol, "trade_date": date.fromisoformat(day), "close": close}
            for symbol, close in (("SPY", D("100")), ("KTOS", D("50")))
            for day in ("2026-08-27", "2026-08-28", "2026-08-31")
        ),
    )

    assert comparison.actual.points[1].value == D("10000")
    assert comparison.actual.points[1].valuation_subtype == "position_replay"


def test_replay_includes_same_day_activity_after_the_left_anchor_instant() -> None:
    comparison = build_performance_comparison(
        balance_history=(
            _balance("a", "...1234", "left", "2026-08-27T18:00:00+00:00", "10000"),
            _balance("a", "...1234", "right", "2026-08-31T20:30:00+00:00", "12000"),
        ),
        position_history=(
            _position("a", "left", "2026-08-27T18:00:00+00:00", "5000"),
            {
                **_position("a", "right", "2026-08-31T20:30:00+00:00", "12000"),
                "net_quantity": D("200"),
            },
        ),
        executions=(
            {
                "external_key": "same-day-buy",
                "account_id": "a",
                "occurred_at": datetime.fromisoformat("2026-08-27T19:00:00+00:00"),
                "asset_type": "EQUITY",
                "symbol": "KTOS",
                "side": "BUY",
                "quantity": D("100"),
                "price": D("50"),
                "net_cash": D("-5000"),
            },
        ),
        cash_movements=(),
        daily_bars=tuple(
            {"symbol": symbol, "trade_date": date.fromisoformat(day), "close": close}
            for symbol, close in (("SPY", D("100")), ("KTOS", D("60")))
            for day in ("2026-08-27", "2026-08-28", "2026-08-31")
        ),
    )

    assert comparison.actual.points[1].date == date(2026, 8, 28)
    assert comparison.actual.points[1].value == D("12000")
    assert comparison.actual.points[1].raw_reconstructed_value == D("12000")


def test_unknown_option_standardness_forces_an_endpoint_bridge() -> None:
    option = {
        **_position("a", "left", "2026-08-27T20:30:00+00:00", "-500"),
        "symbol": "KTOS  260918P00050000",
        "asset_type": "OPTION",
        "net_quantity": D("-1"),
        "contract_multiplier": D("100"),
        "is_non_standard": None,
        "option_type": "PUT",
        "underlying_symbol": "KTOS",
        "strike": D("50"),
    }
    comparison = build_performance_comparison(
        balance_history=(
            _balance("a", "...1234", "left", "2026-08-27T20:30:00+00:00", "10000"),
            _balance("a", "...1234", "right", "2026-08-31T20:30:00+00:00", "10100"),
        ),
        position_history=(option,),
        cash_movements=(),
        daily_bars=tuple(
            {"symbol": "SPY", "trade_date": date.fromisoformat(day), "close": D("100")}
            for day in ("2026-08-27", "2026-08-28", "2026-08-31")
        ),
    )

    assert comparison.actual.points[1].valuation_subtype == "endpoint_bridge"
    assert comparison.actual.points[1].value_quality == "estimated"


def test_unknown_mid_gap_option_multiplier_forces_endpoint_bridge() -> None:
    symbol = "CVX  260918C00215000"
    opened = _option_execution(symbol=symbol, occurred="2026-08-28T10:00:00-04:00")
    opened.update(
        side="SELL",
        net_cash=D("300"),
        price=D("3"),
        is_non_standard=None,
    )
    opened.pop("contract_multiplier")
    closed = _option_execution(symbol=symbol, occurred="2026-08-28T11:00:00-04:00")
    closed.update(net_cash=D("-250"), price=D("2.5"), is_non_standard=None)
    closed.pop("contract_multiplier")
    comparison = build_performance_comparison(
        balance_history=(
            _balance("a", "...1234", "left", "2026-08-27T20:30:00+00:00", "10000"),
            _balance("a", "...1234", "right", "2026-08-31T20:30:00+00:00", "10050"),
        ),
        position_history=(),
        executions=(opened, closed),
        cash_movements=(),
        daily_bars=tuple(
            {"symbol": "SPY", "trade_date": date.fromisoformat(day), "close": D("100")}
            for day in ("2026-08-27", "2026-08-28", "2026-08-31")
        ),
    )

    assert comparison.actual.points[1].valuation_subtype == "endpoint_bridge"


def test_unknown_execution_side_is_not_guessed_as_a_buy() -> None:
    comparison = build_performance_comparison(
        balance_history=(
            _balance("a", "...1234", "left", "2026-08-27T20:30:00+00:00", "10000"),
            _balance("a", "...1234", "right", "2026-08-31T20:30:00+00:00", "10000"),
        ),
        position_history=(
            _position("a", "left", "2026-08-27T20:30:00+00:00", "5000"),
            {
                **_position("a", "right", "2026-08-31T20:30:00+00:00", "10000"),
                "net_quantity": D("200"),
            },
        ),
        executions=(
            {
                "external_key": "unknown-side",
                "account_id": "a",
                "occurred_at": datetime.fromisoformat("2026-08-28T10:00:00-04:00"),
                "asset_type": "EQUITY",
                "symbol": "KTOS",
                "side": "UNKNOWN",
                "quantity": D("100"),
                "price": D("50"),
                "net_cash": D("-5000"),
            },
        ),
        cash_movements=(),
        daily_bars=tuple(
            {"symbol": symbol, "trade_date": date.fromisoformat(day), "close": close}
            for symbol, close in (("SPY", D("100")), ("KTOS", D("50")))
            for day in ("2026-08-27", "2026-08-28", "2026-08-31")
        ),
    )

    assert comparison.actual.points[1].valuation_subtype == "endpoint_bridge"


def test_execution_without_cash_or_price_does_not_move_shares_for_free() -> None:
    comparison = build_performance_comparison(
        balance_history=(
            _balance("a", "...1234", "left", "2026-08-27T20:30:00+00:00", "10000"),
            _balance("a", "...1234", "right", "2026-08-31T20:30:00+00:00", "15000"),
        ),
        position_history=(
            _position("a", "left", "2026-08-27T20:30:00+00:00", "5000"),
            {
                **_position("a", "right", "2026-08-31T20:30:00+00:00", "10000"),
                "net_quantity": D("200"),
            },
        ),
        executions=(
            {
                "external_key": "missing-cash-and-price",
                "account_id": "a",
                "occurred_at": datetime.fromisoformat("2026-08-28T10:00:00-04:00"),
                "asset_type": "EQUITY",
                "symbol": "KTOS",
                "side": "BUY",
                "quantity": D("100"),
            },
        ),
        cash_movements=(),
        daily_bars=tuple(
            {"symbol": symbol, "trade_date": date.fromisoformat(day), "close": close}
            for symbol, close in (("SPY", D("100")), ("KTOS", D("50")))
            for day in ("2026-08-27", "2026-08-28", "2026-08-31")
        ),
    )

    assert comparison.actual.points[1].valuation_subtype == "endpoint_bridge"


def test_etf_execution_replays_as_equity_between_account_anchors() -> None:
    right_position = {
        **_position("a", "right", "2026-08-31T20:30:00+00:00", "1000"),
        "symbol": "QQQ",
        "asset_type": " ETF ",
        "net_quantity": D("10"),
    }
    comparison = build_performance_comparison(
        balance_history=(
            _balance("a", "...1234", "left", "2026-08-27T20:30:00+00:00", "10000"),
            _balance("a", "...1234", "right", "2026-08-31T20:30:00+00:00", "10000"),
        ),
        position_history=(right_position,),
        executions=(
            {
                "external_key": "etf-buy",
                "account_id": "a",
                "occurred_at": datetime.fromisoformat("2026-08-28T10:00:00-04:00"),
                "asset_type": "etf",
                "symbol": "QQQ",
                "side": "BUY",
                "quantity": D("10"),
                "price": D("100"),
                "net_cash": D("-1000"),
            },
        ),
        cash_movements=(),
        daily_bars=tuple(
            {"symbol": symbol, "trade_date": date.fromisoformat(day), "close": D("100")}
            for symbol in ("SPY", "QQQ")
            for day in ("2026-08-27", "2026-08-28", "2026-08-31")
        ),
    )

    assert comparison.actual.points[1].value == D("10000")
    assert comparison.actual.points[1].valuation_subtype == "position_replay"


def test_naive_activity_strings_preserve_date_only_eastern_semantics() -> None:
    date_only = _activity_timestamp("2026-08-28T00:00:00")
    timed = _activity_timestamp("2026-08-28T00:30:00")

    assert date_only is not None and date_only.utcoffset() == -timedelta(hours=4)
    assert timed is not None and timed.utcoffset() == timedelta(0)


def test_execution_price_marks_round_trip_option_missing_from_both_anchors() -> None:
    symbol = "CVX  260918C00215000"
    comparison = build_performance_comparison(
        balance_history=(
            _balance("a", "...1234", "left", "2026-08-31T20:30:00+00:00", "10000"),
            _balance("a", "...1234", "right", "2026-09-03T20:30:00+00:00", "10050"),
        ),
        position_history=(
            _position("a", "left", "2026-08-31T20:30:00+00:00", "5000"),
            _position("a", "right", "2026-09-03T20:30:00+00:00", "5000"),
        ),
        executions=(
            {
                **_option_execution(symbol=symbol, occurred="2026-09-01T14:48:20-04:00"),
                "side": "SELL",
                "net_cash": D("300"),
                "price": D("3"),
            },
            {
                **_option_execution(symbol=symbol, occurred="2026-09-03T11:37:00-04:00"),
                "side": "BUY",
                "net_cash": D("-250"),
                "price": D("2.5"),
            },
        ),
        cash_movements=(),
        daily_bars=tuple(
            {"symbol": item, "trade_date": date.fromisoformat(day), "close": close}
            for item, close in (("SPY", D("100")), ("KTOS", D("50")))
            for day in ("2026-08-31", "2026-09-01", "2026-09-02", "2026-09-03")
        ),
    )

    synthetic = comparison.actual.points[1:-1]
    assert synthetic
    assert all(point.valuation_subtype != "endpoint_bridge" for point in synthetic)
    assert all(point.price_coverage_percent == D("100") for point in synthetic)


def test_exact_flow_window_includes_after_left_and_excludes_after_right() -> None:
    calendar = build_market_calendar(
        tuple(
            {"symbol": "SPY", "trade_date": date.fromisoformat(day), "close": D("100")}
            for day in ("2026-08-27", "2026-08-28")
        )
    )
    points = build_time_weighted_returns(
        (
            _balance("a", "...1234", "left", "2026-08-27T18:00:00+00:00", "100"),
            _balance("a", "...1234", "right", "2026-08-28T20:00:00+00:00", "150"),
        ),
        (
            {
                "account_id": "a",
                "movement_type": "transfer",
                "occurred_at": datetime.fromisoformat("2026-08-27T19:00:00+00:00"),
                "amount": D("50"),
            },
            {
                "account_id": "a",
                "movement_type": "transfer",
                "occurred_at": datetime.fromisoformat("2026-08-28T20:30:00+00:00"),
                "amount": D("25"),
            },
        ),
        calendar=calendar,
    )

    assert points[1].external_flow == D("50")
    assert points[1].daily_return_percent == D("0")
    assert points[1].return_quality == "estimated"


def test_terminal_holding_mismatch_bridges_only_the_affected_account() -> None:
    balances = (
        _balance("account-a", "...1111", "left", "2026-08-27T20:30:00+00:00", "10000"),
        _balance("account-b", "...2222", "left", "2026-08-27T20:30:00+00:00", "20000"),
        _balance("account-a", "...1111", "right", "2026-08-31T20:30:00+00:00", "10000"),
        _balance("account-b", "...2222", "right", "2026-08-31T20:30:00+00:00", "20000"),
    )
    positions = (
        _position("account-a", "left", "2026-08-27T20:30:00+00:00", "5000"),
        {
            **_position("account-a", "right", "2026-08-31T20:30:00+00:00", "6000"),
            "net_quantity": D("120"),
        },
        {
            **_position("account-b", "left", "2026-08-27T20:30:00+00:00", "5000"),
            "symbol": "CVX",
        },
        {
            **_position("account-b", "right", "2026-08-31T20:30:00+00:00", "5000"),
            "symbol": "CVX",
        },
    )
    bars = tuple(
        {"symbol": symbol, "trade_date": date.fromisoformat(day), "close": close}
        for symbol, close in (("SPY", D("100")), ("KTOS", D("50")), ("CVX", D("50")))
        for day in ("2026-08-27", "2026-08-28", "2026-08-31")
    )
    reconstructed = build_reconstructed_balance_history(
        balance_history=balances,
        position_history=positions,
        daily_bars=bars,
        executions=(),
        cash_movements=(),
        lifecycle_events=(),
        calendar=build_market_calendar(bars),
    )

    synthetic = {row["account_id"]: row for row in reconstructed if row.get("synthetic")}
    assert synthetic["account-a"]["valuation_subtype"] == "endpoint_bridge"
    assert synthetic["account-b"]["valuation_subtype"] == "position_replay"


def test_accountless_activity_replays_when_only_one_account_can_own_it() -> None:
    balances = (
        _balance("account-a", "...1111", "left", "2026-08-27T20:30:00+00:00", "10000"),
        _balance("account-a", "...1111", "right", "2026-08-31T20:30:00+00:00", "10000"),
    )
    right = _position("account-a", "right", "2026-08-31T20:30:00+00:00", "5050")
    right["net_quantity"] = D("101")
    positions = (
        _position("account-a", "left", "2026-08-27T20:30:00+00:00", "5000"),
        right,
    )
    bars = tuple(
        {"symbol": symbol, "trade_date": date.fromisoformat(day), "close": close}
        for symbol, close in (("SPY", D("100")), ("KTOS", D("50")))
        for day in ("2026-08-27", "2026-08-28", "2026-08-31")
    )
    reconstructed = build_reconstructed_balance_history(
        balance_history=balances,
        position_history=positions,
        daily_bars=bars,
        executions=(
            {
                "occurred_at": datetime.fromisoformat("2026-08-28T15:00:00+00:00"),
                "asset_type": "EQUITY",
                "symbol": "KTOS",
                "side": "BUY",
                "quantity": D("1"),
                "price": D("50"),
                "net_cash": D("-50"),
            },
        ),
        cash_movements=(),
        lifecycle_events=(),
        calendar=build_market_calendar(bars),
    )

    synthetic = next(row for row in reconstructed if row.get("synthetic"))
    assert synthetic["account_id"] == "account-a"
    assert synthetic["valuation_subtype"] == "position_replay"
    assert synthetic["liquidation_value"] == D("10000")


def test_multi_account_gap_with_accountless_activity_stays_unresolved() -> None:
    balances = (
        _balance("account-a", "...1111", "left", "2026-08-27T20:30:00+00:00", "10000"),
        _balance("account-b", "...2222", "left", "2026-08-27T20:30:00+00:00", "20000"),
        _balance("account-a", "...1111", "right", "2026-08-31T20:30:00+00:00", "10000"),
        _balance("account-b", "...2222", "right", "2026-08-31T20:30:00+00:00", "20000"),
    )
    positions = tuple(
        {
            **_position(account, run, observed, "5000"),
            "symbol": symbol,
        }
        for account, symbol in (("account-a", "KTOS"), ("account-b", "CVX"))
        for run, observed in (
            ("left", "2026-08-27T20:30:00+00:00"),
            ("right", "2026-08-31T20:30:00+00:00"),
        )
    )
    bars = tuple(
        {"symbol": symbol, "trade_date": date.fromisoformat(day), "close": close}
        for symbol, close in (("SPY", D("100")), ("KTOS", D("50")), ("CVX", D("50")))
        for day in ("2026-08-27", "2026-08-28", "2026-08-31")
    )
    reconstructed = build_reconstructed_balance_history(
        balance_history=balances,
        position_history=positions,
        daily_bars=bars,
        executions=(),
        cash_movements=(
            {
                "occurred_at": datetime.fromisoformat("2026-08-28T15:00:00+00:00"),
                "movement_type": "transfer",
                "amount": D("25000"),
            },
        ),
        lifecycle_events=(),
        calendar=build_market_calendar(bars),
    )

    assert not any(row.get("synthetic") for row in reconstructed)


def test_lifecycle_quantity_overshoot_forces_endpoint_bridge() -> None:
    option = _option_position(
        run="left",
        observed="2026-08-27T20:30:00+00:00",
        quantity="-1",
        market_value="-100",
    )
    right_option = _option_position(
        run="right",
        observed="2026-08-31T20:30:00+00:00",
        quantity="-1",
        market_value="-100",
    )
    comparison = build_performance_comparison(
        balance_history=(
            _balance("a", "...1234", "left", "2026-08-27T20:30:00+00:00", "10000"),
            _balance("a", "...1234", "right", "2026-08-31T20:30:00+00:00", "10000"),
        ),
        position_history=(option, right_option),
        lifecycle_events=(
            {
                "external_key": "oversize-expiration",
                "account_id": "a",
                "occurred_at": datetime.fromisoformat("2026-08-28T10:00:00-04:00"),
                "event_type": "expiration",
                "symbol": option["symbol"],
                "option_quantity": D("2"),
            },
        ),
        cash_movements=(),
        daily_bars=_option_bars(str(option["symbol"])),
    )

    assert comparison.actual.points[1].valuation_subtype == "endpoint_bridge"


def test_lifecycle_before_execution_is_replayed_in_timestamp_order() -> None:
    left_option = _option_position(
        run="left",
        observed="2026-08-27T20:30:00+00:00",
        quantity="-1",
        market_value="-100",
    )
    right_option = _option_position(
        run="right",
        observed="2026-08-31T20:30:00+00:00",
        quantity="1",
        market_value="100",
    )
    comparison = build_performance_comparison(
        balance_history=(
            _balance("a", "...1234", "left", "2026-08-27T20:30:00+00:00", "10000"),
            _balance("a", "...1234", "right", "2026-08-31T20:30:00+00:00", "10100"),
        ),
        position_history=(left_option, right_option),
        executions=(
            _option_execution(
                symbol=str(left_option["symbol"]),
                occurred="2026-08-28T11:00:00-04:00",
            ),
        ),
        lifecycle_events=(
            {
                "external_key": "expiration-first",
                "account_id": "a",
                "occurred_at": datetime.fromisoformat("2026-08-28T10:00:00-04:00"),
                "event_type": "expiration",
                "symbol": left_option["symbol"],
                "option_quantity": D("1"),
            },
        ),
        cash_movements=(),
        daily_bars=_option_bars(str(left_option["symbol"])),
    )

    assert comparison.actual.points[1].valuation_subtype == "position_replay"


def test_execution_before_lifecycle_is_replayed_in_timestamp_order() -> None:
    symbol = "KTOS  260918P00050000"
    comparison = build_performance_comparison(
        balance_history=(
            _balance("a", "...1234", "left", "2026-08-27T20:30:00+00:00", "10000"),
            _balance("a", "...1234", "right", "2026-08-31T20:30:00+00:00", "9900"),
        ),
        position_history=(),
        executions=(_option_execution(symbol=symbol, occurred="2026-08-28T10:00:00-04:00"),),
        lifecycle_events=(
            {
                "external_key": "expiration-second",
                "account_id": "a",
                "occurred_at": datetime.fromisoformat("2026-08-28T11:00:00-04:00"),
                "event_type": "expiration",
                "symbol": symbol,
                "option_quantity": D("1"),
            },
        ),
        cash_movements=(),
        daily_bars=_option_bars(symbol),
    )

    assert comparison.actual.points[1].valuation_subtype == "position_replay"


def test_equal_timestamp_trade_and_lifecycle_fail_closed() -> None:
    symbol = "KTOS  260918P00050000"
    occurred = "2026-08-28T10:00:00-04:00"
    comparison = build_performance_comparison(
        balance_history=(
            _balance("a", "...1234", "left", "2026-08-27T20:30:00+00:00", "10000"),
            _balance("a", "...1234", "right", "2026-08-31T20:30:00+00:00", "9900"),
        ),
        position_history=(),
        executions=(_option_execution(symbol=symbol, occurred=occurred),),
        lifecycle_events=(
            {
                "external_key": "same-instant-expiration",
                "account_id": "a",
                "occurred_at": datetime.fromisoformat(occurred),
                "event_type": "expiration",
                "symbol": symbol,
                "option_quantity": D("1"),
            },
        ),
        cash_movements=(),
        daily_bars=_option_bars(symbol),
    )

    assert comparison.actual.points[1].valuation_subtype == "endpoint_bridge"


def test_date_only_lifecycle_with_same_session_trade_fails_closed() -> None:
    left_option = _option_position(
        run="left",
        observed="2026-08-27T20:30:00+00:00",
        quantity="-1",
        market_value="-100",
    )
    right_option = _option_position(
        run="right",
        observed="2026-08-31T20:30:00+00:00",
        quantity="1",
        market_value="100",
    )
    comparison = build_performance_comparison(
        balance_history=(
            _balance("a", "...1234", "left", "2026-08-27T20:30:00+00:00", "10000"),
            _balance("a", "...1234", "right", "2026-08-31T20:30:00+00:00", "10100"),
        ),
        position_history=(left_option, right_option),
        executions=(
            _option_execution(
                symbol=str(left_option["symbol"]),
                occurred="2026-08-28T11:00:00-04:00",
            ),
        ),
        lifecycle_events=(
            {
                "external_key": "date-only-expiration",
                "account_id": "a",
                # SQLite returns the mapper's date-only midnight without an offset.
                "occurred_at": datetime(2026, 8, 28),
                "event_type": "expiration",
                "symbol": left_option["symbol"],
                "option_quantity": D("1"),
            },
        ),
        cash_movements=(),
        daily_bars=_option_bars(str(left_option["symbol"])),
    )

    assert comparison.actual.points[1].valuation_subtype == "endpoint_bridge"


def test_synthetic_close_uses_market_timezone_in_winter() -> None:
    balances = (
        _balance("a", "...1234", "left", "2026-01-14T21:30:00+00:00", "10000"),
        _balance("a", "...1234", "right", "2026-01-16T21:30:00+00:00", "10000"),
    )
    positions = (
        _position("a", "left", "2026-01-14T21:30:00+00:00", "5000"),
        _position("a", "right", "2026-01-16T21:30:00+00:00", "5000"),
    )
    bars = tuple(
        {"symbol": symbol, "trade_date": date.fromisoformat(day), "close": D("50")}
        for symbol in ("SPY", "KTOS")
        for day in ("2026-01-14", "2026-01-15", "2026-01-16")
    )
    reconstructed = build_reconstructed_balance_history(
        balance_history=balances,
        position_history=positions,
        daily_bars=bars,
        executions=(),
        cash_movements=(),
        lifecycle_events=(),
        calendar=build_market_calendar(bars),
    )

    synthetic = next(row for row in reconstructed if row.get("synthetic"))
    assert synthetic["observed_at"].hour == 16
    assert synthetic["observed_at"].utcoffset() == -timedelta(hours=5)


def test_zero_equity_close_uses_endpoint_bridge_instead_of_a_fake_crash() -> None:
    balances = (
        _balance("a", "...1234", "left", "2026-08-27T20:30:00+00:00", "10000"),
        _balance("a", "...1234", "right", "2026-08-31T20:30:00+00:00", "10100"),
    )
    positions = (
        _position("a", "left", "2026-08-27T20:30:00+00:00", "5000"),
        _position("a", "right", "2026-08-31T20:30:00+00:00", "5100"),
    )
    bars = tuple(
        {
            "symbol": symbol,
            "trade_date": date.fromisoformat(day),
            "close": D(close),
        }
        for symbol, prices in {
            "SPY": (("2026-08-27", "100"), ("2026-08-28", "100"), ("2026-08-31", "100")),
            "KTOS": (("2026-08-27", "50"), ("2026-08-28", "0"), ("2026-08-31", "51")),
        }.items()
        for day, close in prices
    )

    reconstructed = build_reconstructed_balance_history(
        balance_history=balances,
        position_history=positions,
        daily_bars=bars,
        executions=(),
        cash_movements=(),
        lifecycle_events=(),
        calendar=build_market_calendar(bars),
    )

    synthetic = next(row for row in reconstructed if row.get("synthetic"))
    assert synthetic["valuation_subtype"] == "endpoint_bridge"
    assert synthetic["raw_reconstructed_value"] is None
    assert synthetic["liquidation_value"] > D("0")


def _balance(
    account_id: str,
    account_mask: str,
    run: str,
    observed: str,
    value: str,
) -> dict[str, object]:
    return {
        "account_id": account_id,
        "account_mask": account_mask,
        "sync_run_id": run,
        "observed_at": datetime.fromisoformat(observed),
        "liquidation_value": D(value),
    }


def _position(
    account_id: str,
    run: str,
    observed: str,
    market_value: str,
) -> dict[str, object]:
    return {
        "account_id": account_id,
        "account_mask": "...1234",
        "sync_run_id": run,
        "observed_at": datetime.fromisoformat(observed).astimezone(UTC),
        "symbol": "KTOS",
        "asset_type": "EQUITY",
        "net_quantity": D("100"),
        "market_value": D(market_value),
    }


def _option_position(
    *,
    run: str,
    observed: str,
    quantity: str,
    market_value: str,
) -> dict[str, object]:
    return {
        **_position("a", run, observed, market_value),
        "symbol": "KTOS  260918P00050000",
        "asset_type": "OPTION",
        "net_quantity": D(quantity),
        "contract_multiplier": D("100"),
        "is_non_standard": False,
        "option_type": "PUT",
        "underlying_symbol": "KTOS",
        "strike": D("50"),
    }


def _option_execution(*, symbol: str, occurred: str) -> dict[str, object]:
    return {
        "external_key": f"buy-{occurred}",
        "account_id": "a",
        "occurred_at": datetime.fromisoformat(occurred),
        "asset_type": "OPTION",
        "symbol": symbol,
        "side": "BUY",
        "quantity": D("1"),
        "price": D("1"),
        "net_cash": D("-100"),
        "contract_multiplier": D("100"),
        "is_non_standard": False,
        "option_type": "PUT",
        "underlying_symbol": "KTOS",
        "strike": D("50"),
    }


def _option_bars(symbol: str) -> tuple[dict[str, object], ...]:
    return tuple(
        {"symbol": item, "trade_date": date.fromisoformat(day), "close": close}
        for item, close in (("SPY", D("100")), ("KTOS", D("50")), (symbol, D("1")))
        for day in ("2026-08-27", "2026-08-28", "2026-08-31")
    )
