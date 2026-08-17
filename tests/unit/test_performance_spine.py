from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from schwab_dashboard.application.performance.assignments import (
    calculate_assignment_impact,
)
from schwab_dashboard.application.performance.capital import calculate_capital_efficiency
from schwab_dashboard.application.performance.economics import calculate_option_economics
from schwab_dashboard.application.performance.models import ReturnPoint
from schwab_dashboard.application.performance.risk import calculate_risk_statistics

D = Decimal


def test_risk_statistics_use_chained_return_path() -> None:
    points = (
        _point("2026-08-10", "100000", None),
        _point("2026-08-11", "102000", "2"),
        _point("2026-08-12", "96900", "-5"),
        _point("2026-08-13", "98838", "2"),
    )

    result = calculate_risk_statistics(points)

    assert result.status == "early_sample"
    assert result.observations == 3
    assert result.max_drawdown_percent == D("-5.00")
    assert result.positive_day_percent == D("66.66666666666666666666666667")
    assert result.worst_day_percent == D("-5")
    assert result.annualized_volatility_percent is not None


def test_option_economics_separates_cash_closed_result_and_open_mark() -> None:
    executions = (
        _execution("open", "sell", "opening", "200", "199", "1"),
        _execution("close", "buy", "closing", "50", "-51", "1"),
    )
    positions = (
        {
            "account_mask": "...1234",
            "observed_at": datetime(2026, 8, 13, 20, tzinfo=UTC),
            "asset_type": "OPTION",
            "net_quantity": D("-1"),
            "market_value": D("-80"),
            "short_open_profit_loss": D("20"),
        },
    )

    result = calculate_option_economics(
        executions=executions,
        lifecycle_events=(),
        position_history=positions,
        coverage_start=date(2026, 8, 1),
        coverage_end=date(2026, 8, 31),
    )

    assert result.opening_credits == D("200")
    assert result.closing_debits == D("50")
    assert result.fees == D("2")
    assert result.net_executed_cash == D("148")
    assert result.closed_campaign_result == D("148")
    assert result.closed_campaigns == 1
    assert result.open_mark_profit_loss == D("20")
    assert result.current_option_liability == D("80")
    assert result.campaign_cash_variance == D("0")


def test_option_economics_limits_completed_campaigns_to_return_window() -> None:
    executions = (
        _execution_on("old-open", "sell", "opening", "100", "100", "0", 1),
        _execution_on("old-close", "buy", "closing", "25", "-25", "0", 2),
        _execution_on("new-open", "sell", "opening", "200", "200", "0", 10),
        _execution_on("new-close", "buy", "closing", "50", "-50", "0", 11),
    )

    result = calculate_option_economics(
        executions=executions,
        lifecycle_events=(),
        position_history=(),
        coverage_start=date(2026, 8, 10),
        coverage_end=date(2026, 8, 14),
    )

    assert result.net_executed_cash == D("150")
    assert result.closed_campaign_result == D("150")
    assert result.closed_campaigns == 1


def test_capital_efficiency_keeps_account_maintenance_separate() -> None:
    result = calculate_capital_efficiency(
        actual_points=(
            _point("2026-08-11", "100000", None),
            _point("2026-08-12", "102000", "2"),
        ),
        balance_history=(
            {
                "account_mask": "...1234",
                "observed_at": datetime(2026, 8, 12, 20, tzinfo=UTC),
                "liquidation_value": D("102000"),
                "maintenance_requirement": D("20400"),
                "buying_power": D("50000"),
                "available_funds": D("25000"),
            },
        ),
        net_option_cash=D("1010"),
    )

    assert result.average_net_liquidation == D("101000")
    assert result.option_cash_on_average_capital_percent == D("1.00")
    assert result.maintenance_to_net_liquidation_percent == D("20.0")
    assert result.available_funds == D("25000")


def test_assignment_impact_labels_called_away_upside_as_reference() -> None:
    result = calculate_assignment_impact(
        lifecycle_events=(
            {
                "event_type": "assignment",
                "option_side": "call",
                "occurred_at": datetime(2026, 8, 12, 20, tzinfo=UTC),
                "underlying_symbol": "CVX",
                "strike": D("195"),
                "option_quantity": D("2"),
                "stock_quantity": D("200"),
            },
        ),
        daily_bars=(
            {"symbol": "CVX", "trade_date": date(2026, 8, 13), "close": D("201")},
        ),
        coverage_start=date(2026, 8, 1),
        coverage_end=date(2026, 8, 13),
    )

    assert result.status == "ready"
    assert result.assigned_call_contracts == 2
    assert result.called_away_shares == 200
    assert result.period_end_upside_reference == D("1200")


def _point(day: str, value: str, daily_return: str | None) -> ReturnPoint:
    return ReturnPoint(
        date=date.fromisoformat(day),
        value=D(value),
        external_flow=D("0"),
        daily_return_percent=D(daily_return) if daily_return is not None else None,
        cumulative_return_percent=None,
        quality="observed",
    )


def _execution(
    key: str,
    side: str,
    effect: str,
    gross: str,
    net_cash: str,
    fees: str,
) -> dict[str, object]:
    return {
        "external_key": key,
        "order_external_key": key,
        "account_mask": "...1234",
        "occurred_at": datetime(2026, 8, 10 if key == "open" else 11, 20, tzinfo=UTC),
        "asset_type": "option",
        "symbol": "CVX  260821C00200000",
        "underlying_symbol": "CVX",
        "option_side": "call",
        "side": side,
        "position_effect": effect,
        "quantity": D("1"),
        "gross_amount": D(gross),
        "net_cash": D(net_cash),
        "fees": D(fees),
    }


def _execution_on(
    key: str,
    side: str,
    effect: str,
    gross: str,
    net_cash: str,
    fees: str,
    day: int,
) -> dict[str, object]:
    row = _execution(key, side, effect, gross, net_cash, fees)
    row["occurred_at"] = datetime(2026, 8, day, 20, tzinfo=UTC)
    return row
