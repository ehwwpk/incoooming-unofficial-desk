from datetime import date
from decimal import Decimal

from schwab_dashboard.application.dashboard.calculations import (
    account_day_profit_loss,
    summarize_portfolio,
)
from schwab_dashboard.application.dashboard.models import PositionSummary
from schwab_dashboard.application.performance.models import ReturnPoint

D = Decimal


def test_account_day_matches_latest_results_link_in_dollars_and_percent() -> None:
    points = (
        _point("2026-08-21", "134118.18", None, "0", "observed_anchor"),
        _point("2026-08-24", "128721.82", "-4.023586", "0", "linked"),
    )

    account_day = account_day_profit_loss(points)

    assert account_day.status == "linked"
    assert account_day.profit_loss == D("-5396.36")
    assert account_day.profit_loss_percent == D("-4.023586")
    assert account_day.as_of == date(2026, 8, 24)
    assert account_day.previous_as_of == date(2026, 8, 21)


def test_account_day_subtracts_owner_flow_but_keeps_market_profit() -> None:
    account_day = account_day_profit_loss(
        (
            _point("2026-08-11", "100000", None, "0", "observed_anchor"),
            _point("2026-08-12", "126000", "1", "25000", "linked"),
        )
    )

    assert account_day.profit_loss == D("1000")
    assert account_day.external_cash_flow == D("25000")


def test_account_day_fails_closed_when_account_coverage_changed() -> None:
    account_day = account_day_profit_loss(
        (
            _point("2026-08-11", "100000", None, "0", "observed_anchor"),
            _point("2026-08-12", "50000", None, "0", "account_coverage_changed"),
        )
    )

    assert account_day.status == "account_coverage_changed"
    assert account_day.profit_loss is None
    assert account_day.profit_loss_percent is None


def test_account_day_can_link_after_an_older_incomplete_cumulative_path() -> None:
    account_day = account_day_profit_loss(
        (
            _point("2026-08-11", "100000", None, "0", "account_coverage_changed"),
            _point(
                "2026-08-12",
                "101000",
                "1",
                "0",
                "linked_after_incomplete_history",
            ),
        )
    )

    assert account_day.status == "linked"
    assert account_day.profit_loss == D("1000")
    assert account_day.profit_loss_percent == D("1")


def test_portfolio_keeps_account_day_primary_and_open_positions_as_reconciliation() -> None:
    position = PositionSummary(
        account_mask="...1234",
        symbol="KTOS",
        description="Kratos Defense",
        asset_type="EQUITY",
        quantity=D("1100"),
        average_price=D("40"),
        mark=D("53.26"),
        market_value=D("58586"),
        day_profit_loss=D("-4740.79"),
        day_profit_loss_percent=D("-7.5"),
        strategy=None,
    )
    account_day = account_day_profit_loss(
        (
            _point("2026-08-21", "134118.18", None, "0", "observed_anchor"),
            _point("2026-08-24", "128721.82", "-4.023586", "0", "linked"),
        )
    )

    summary = summarize_portfolio(
        (position,),
        ({"liquidation_value": D("128721.82")},),
        account_day=account_day,
    )

    assert summary.day_profit_loss == D("-5396.36")
    assert summary.day_profit_loss_percent == D("-4.023586")
    assert summary.day_profit_loss_source == "net_liquidation"
    assert summary.open_position_day_profit_loss == D("-4740.79")
    assert summary.day_profit_loss_reconciliation_gap == D("655.57")
    assert summary.day_profit_loss_reconciliation_status == "diverged"


def _point(
    day: str,
    value: str,
    daily_return: str | None,
    flow: str,
    quality: str,
) -> ReturnPoint:
    daily = D(daily_return) if daily_return is not None else None
    return ReturnPoint(
        date=date.fromisoformat(day),
        value=D(value),
        external_flow=D(flow),
        daily_return_percent=daily,
        cumulative_return_percent=daily,
        quality=quality,
    )
