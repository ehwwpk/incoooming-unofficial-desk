from datetime import UTC, date, datetime
from decimal import Decimal

from schwab_dashboard.application.dashboard.live_performance import build_live_performance
from schwab_dashboard.application.dashboard.live_positions import build_live_position_book
from schwab_dashboard.application.dashboard.short_premium import (
    is_short_premium_execution,
    option_cash_action_label,
)
from schwab_dashboard.infrastructure.demo.dashboard import DemoDashboardReader

D = Decimal


def test_short_premium_helper_accepts_puts_and_rejects_equity_and_stc() -> None:
    assert is_short_premium_execution(_option("put", "sell", "opening"))
    assert is_short_premium_execution(_option("put", "buy", "closing"))
    assert is_short_premium_execution(_option("call", "sell", "opening"))
    assert not is_short_premium_execution(_option("call", "sell", "closing"))
    assert not is_short_premium_execution(
        {
            "asset_type": "equity",
            "side": "sell",
            "position_effect": "opening",
        }
    )
    assert option_cash_action_label(_option("put", "sell", "opening")) == "PUT SOLD"
    assert option_cash_action_label(_option("put", "buy", "closing")) == "PUT CLOSED"


def test_put_credit_lands_in_desk_window_capture_and_activity_not_dividends() -> None:
    as_of = date(2026, 8, 11)
    snapshot = DemoDashboardReader().execute()
    projection = build_live_performance(
        executions=(
            _option(
                "put",
                "sell",
                "opening",
                net_cash="120",
                gross="120",
                occurred=datetime(2026, 8, 10, 15, tzinfo=UTC),
            ),
        ),
        cash_movements=(),
        lifecycle_events=(),
        live_book=build_live_position_book(snapshot.positions, as_of=as_of),
        covered_capital=D("100000"),
        as_of=as_of,
    )
    month = {window.key: window for window in projection.performance_windows}["month"]
    assert month.option_cash == D("120")
    assert month.gross_premium == D("120")
    assert month.premium_capture_percent == D("100")
    assert month.dividends == D("0")
    assert projection.cash_events[0].action_label == "PUT SOLD"
    assert projection.cash_events[0].amount == D("120")


def test_premium_capture_uses_fee_net_cash() -> None:
    as_of = date(2026, 8, 11)
    snapshot = DemoDashboardReader().execute()
    execution = {
        **_option(
            "call",
            "sell",
            "opening",
            net_cash="119",
            gross="120",
            occurred=datetime(2026, 8, 10, 15, tzinfo=UTC),
        ),
        "fees": D("1"),
    }

    projection = build_live_performance(
        executions=(execution,),
        cash_movements=(),
        lifecycle_events=(),
        live_book=build_live_position_book(snapshot.positions, as_of=as_of),
        covered_capital=D("100000"),
        as_of=as_of,
    )

    month = projection.performance_windows[0]
    assert month.option_cash == D("119")
    assert month.premium_capture_percent == D("119") / D("120") * D("100")


def test_yield_is_unknown_when_covered_capital_is_missing() -> None:
    as_of = date(2026, 8, 11)
    snapshot = DemoDashboardReader().execute()
    projection = build_live_performance(
        executions=(
            _option(
                "call",
                "sell",
                "opening",
                net_cash="120",
                gross="120",
            ),
        ),
        cash_movements=(),
        lifecycle_events=(),
        live_book=build_live_position_book(snapshot.positions, as_of=as_of),
        covered_capital=None,
        as_of=as_of,
    )

    assert all(window.annualized_option_yield is None for window in projection.performance_windows)
    assert all(window.annualized_total_yield is None for window in projection.performance_windows)
    assert projection.monthly_performance[-1].average_covered_capital is None
    assert projection.covered_calls.annualized_option_yield is None
    assert projection.covered_calls.annualized_total_cash_yield is None


def test_live_assignment_summaries_use_aliases_and_delivered_share_facts() -> None:
    as_of = date(2026, 8, 11)
    snapshot = DemoDashboardReader().execute()
    projection = build_live_performance(
        executions=(),
        cash_movements=(),
        lifecycle_events=(
            {
                "external_key": "call-assigned",
                "occurred_at": datetime(2026, 8, 10, 15, tzinfo=UTC),
                "event_type": "ASSIGNED",
                "option_side": "C",
                "option_quantity": D("2"),
                "stock_quantity": D("150.5"),
            },
            {
                "external_key": "put-assigned",
                "occurred_at": datetime(2026, 8, 10, 16, tzinfo=UTC),
                "event_type": "assignment",
                "option_side": "PUT",
                "option_quantity": D("1"),
                "multiplier": D("10"),
            },
        ),
        live_book=build_live_position_book(snapshot.positions, as_of=as_of),
        covered_capital=D("100000"),
        as_of=as_of,
    )

    month = projection.monthly_performance[-1]
    assert month.assigned_contracts == 3
    assert month.called_away_shares == D("150.5")
    assert month.acquired_shares == 10
    assert projection.covered_calls.assigned_contracts == 2
    assert projection.covered_calls.called_away_shares == D("150.5")


def _option(
    side: str,
    trade_side: str,
    effect: str,
    *,
    net_cash: str = "120",
    gross: str = "120",
    occurred: datetime | None = None,
) -> dict[str, object]:
    return {
        "external_key": f"{side}-{trade_side}-{effect}",
        "occurred_at": occurred or datetime(2026, 8, 10, 15, tzinfo=UTC),
        "asset_type": "option",
        "option_side": side,
        "side": trade_side,
        "position_effect": effect,
        "gross_amount": D(gross),
        "net_cash": D(net_cash),
        "quantity": 1,
        "underlying_symbol": "KTOS",
        "symbol": "KTOS  260821P00060000",
        "fees": D("0"),
    }
