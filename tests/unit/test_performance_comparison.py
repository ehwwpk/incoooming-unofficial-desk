from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from schwab_dashboard.application.performance.projection import build_performance_comparison

D = Decimal


def test_time_weighted_return_excludes_deposit_before_chaining() -> None:
    comparison = build_performance_comparison(
        balance_history=(
            _balance("2026-08-11T20:00:00+00:00", "100000", "99000"),
            _balance("2026-08-12T20:00:00+00:00", "126000", "100000"),
            _balance("2026-08-13T20:00:00+00:00", "127260", "126000"),
        ),
        cash_movements=(
            {
                "occurred_at": datetime(2026, 8, 12, 18, tzinfo=UTC),
                "movement_type": "transfer",
                "amount": D("25000"),
            },
        ),
    )

    assert comparison.external_flows_excluded == D("25000")
    assert [point.daily_return_percent for point in comparison.actual.points] == [
        D("1.010101010101010101010101010"),
        D("1.00"),
        D("1.00"),
    ]
    assert comparison.actual.return_percent == D("3.040404040404040404040404000")
    assert comparison.shares_without_options.status == "not_available"
    assert comparison.market_reference.return_percent is None


def test_comparison_refuses_to_invent_missing_benchmarks() -> None:
    comparison = build_performance_comparison(balance_history=(), cash_movements=())

    assert comparison.actual.status == "waiting"
    assert comparison.actual.return_percent is None
    assert all(
        series.status == "not_available"
        for series in (
            comparison.shares_without_options,
            comparison.option_overlay,
            comparison.market_reference,
        )
    )


def test_comparison_derives_static_starting_shares_and_executed_overlay() -> None:
    comparison = build_performance_comparison(
        balance_history=(
            _balance("2026-08-11T20:00:00+00:00", "100000", "100000"),
            _balance("2026-08-12T20:00:00+00:00", "101000", "100000"),
        ),
        cash_movements=(),
        position_history=(
            {
                "sync_run_id": "run-1",
                "account_mask": "...1234",
                "observed_at": datetime(2026, 8, 11, 20, tzinfo=UTC),
                "symbol": "KTOS",
                "asset_type": "EQUITY",
                "net_quantity": D("100"),
            },
        ),
        daily_bars=(
            {"symbol": "KTOS", "trade_date": datetime(2026, 8, 11).date(), "close": D("60")},
            {"symbol": "KTOS", "trade_date": datetime(2026, 8, 12).date(), "close": D("63")},
        ),
        executions=(
            {
                "occurred_at": datetime(2026, 8, 12, 15, tzinfo=UTC),
                "asset_type": "option",
                "side": "sell",
                "position_effect": "opening",
                "net_cash": D("200"),
            },
        ),
    )

    assert comparison.shares_without_options.status == "derived"
    assert comparison.shares_without_options.return_percent == D("0.3")
    assert comparison.option_overlay.status == "cash_only"
    assert comparison.option_overlay.return_percent == D("0.2")


def test_share_baseline_freezes_inventory_nearest_to_return_window() -> None:
    comparison = build_performance_comparison(
        balance_history=(
            _balance("2026-08-11T20:00:00+00:00", "100000", "100000"),
            _balance("2026-08-12T20:00:00+00:00", "101000", "100000"),
        ),
        cash_movements=(),
        position_history=(
            {
                "sync_run_id": "old",
                "observed_at": datetime(2026, 7, 1, 20, tzinfo=UTC),
                "symbol": "KTOS",
                "asset_type": "EQUITY",
                "net_quantity": D("50"),
            },
            {
                "sync_run_id": "aligned",
                "observed_at": datetime(2026, 8, 11, 18, tzinfo=UTC),
                "symbol": "KTOS",
                "asset_type": "EQUITY",
                "net_quantity": D("100"),
            },
        ),
        daily_bars=(
            {"symbol": "KTOS", "trade_date": datetime(2026, 8, 11).date(), "close": D("60")},
            {"symbol": "KTOS", "trade_date": datetime(2026, 8, 12).date(), "close": D("63")},
        ),
    )

    assert comparison.shares_without_options.status == "derived"
    assert comparison.shares_without_options.return_percent == D("0.3")


def test_market_reference_rejects_materially_partial_history() -> None:
    comparison = build_performance_comparison(
        balance_history=(
            _balance("2026-08-01T20:00:00+00:00", "100000", "100000"),
            _balance("2026-08-12T20:00:00+00:00", "101000", "100000"),
        ),
        cash_movements=(),
        daily_bars=(
            {"symbol": "SPY", "trade_date": datetime(2026, 8, 10).date(), "close": D("640")},
            {"symbol": "SPY", "trade_date": datetime(2026, 8, 12).date(), "close": D("645")},
        ),
    )

    assert comparison.market_reference.status == "not_available"
    assert comparison.market_reference.return_percent is None


def _balance(observed: str, liquidation: str, initial: str) -> dict[str, object]:
    return {
        "account_mask": "...1234",
        "observed_at": datetime.fromisoformat(observed),
        "liquidation_value": D(liquidation),
        "initial_liquidation_value": D(initial),
    }
