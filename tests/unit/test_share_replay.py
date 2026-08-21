from datetime import UTC, date, datetime
from decimal import Decimal

from schwab_dashboard.application.performance.baselines import build_static_share_baseline
from schwab_dashboard.application.performance.models import ReturnPoint
from schwab_dashboard.application.performance.projection import build_performance_comparison
from schwab_dashboard.application.performance.share_replay import (
    apply_discretionary_equity,
    classify_forced_equity,
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
    assert comparison.methodology_version == "incoooming-performance-v3"


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
