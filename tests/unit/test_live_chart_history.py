from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from schwab_dashboard.application.dashboard.live_chart_history import (
    build_option_events,
    build_price_points,
    build_share_trade_events,
)

D = Decimal


def test_resolution_uses_originating_sale_lifecycle() -> None:
    points = build_price_points("KTOS", _bars())
    sale = _option_execution(
        key="sale",
        occurred_at=datetime(2026, 8, 5, 15, tzinfo=UTC),
        side="sell",
        position_effect="opening",
        net_cash=D("200"),
    )
    close = _option_execution(
        key="close",
        occurred_at=datetime(2026, 8, 8, 15, tzinfo=UTC),
        side="buy",
        position_effect="closing",
        net_cash=D("-50"),
    )

    events = build_option_events(
        "KTOS",
        executions=(sale, close),
        lifecycle_events=(),
        points=points,
        current_option_symbols=(),
    )

    assert [event.event_type for event in events] == ["sale", "closed"]
    assert events[0].lifecycle_id == events[1].lifecycle_id == events[0].sequence
    assert events[0].linked_resolution_sequence == events[1].sequence
    assert events[1].linked_sale_sequence == events[0].sequence
    assert events[0].option_value_per_share == D("0.5")
    assert events[0].option_value_vs_credit_percent == D("25.00")
    assert events[1].option_value_vs_credit_percent == D("25.00")
    assert [event.campaign_label for event in events] == ["C1", "C1"]
    assert [event.campaign_leg_index for event in events] == [1, 2]
    assert all(event.campaign_confidence == "exact" for event in events)


def test_open_event_compares_current_mark_with_original_credit() -> None:
    points = build_price_points("KTOS", _bars())
    sale = _option_execution(
        key="sale",
        occurred_at=datetime(2026, 8, 5, 15, tzinfo=UTC),
        side="sell",
        position_effect="opening",
        net_cash=D("200"),
    )

    events = build_option_events(
        "KTOS",
        executions=(sale,),
        lifecycle_events=(),
        points=points,
        current_option_symbols={"KTOS  260918C00065000"},
        current_option_marks={"KTOS  260918C00065000": D("3")},
    )

    assert events[0].outcome == "OPEN"
    assert events[0].option_value_per_share == D("3")
    assert events[0].option_value_vs_credit_percent == D("150.0")


def test_share_fills_net_to_one_marker_per_day() -> None:
    points = build_price_points("KTOS", _bars())
    occurred_at = datetime(2026, 8, 6, 15, tzinfo=UTC)
    executions = (
        _share_execution("buy-1", occurred_at, "buy", D("25"), D("60")),
        _share_execution("buy-2", occurred_at, "buy", D("75"), D("62")),
        _share_execution("sell-1", occurred_at, "sell", D("10"), D("63")),
    )

    events = build_share_trade_events("KTOS", executions=executions, points=points)

    assert [(event.action, event.shares) for event in events] == [("buy", 90)]
    assert events[0].price == D("61.5")
    assert events[0].gross_buys == 100
    assert events[0].gross_sells == 10


def _bars() -> tuple[dict[str, object], ...]:
    start = date(2026, 8, 5)
    return tuple(
        {
            "symbol": "KTOS",
            "trade_date": start + timedelta(days=index),
            "open": D("59"),
            "high": D("63"),
            "low": D("58"),
            "close": D(str(60 + index)),
            "volume": 1000,
        }
        for index in range(6)
    )


def _option_execution(
    *,
    key: str,
    occurred_at: datetime,
    side: str,
    position_effect: str,
    net_cash: Decimal,
) -> dict[str, object]:
    return {
        "external_key": key,
        "order_external_key": key,
        "occurred_at": occurred_at,
        "side": side,
        "position_effect": position_effect,
        "quantity": D("1"),
        "price": D("2") if side == "sell" else D("0.5"),
        "gross_amount": abs(net_cash),
        "net_cash": net_cash,
        "asset_type": "option",
        "symbol": "KTOS  260918C00065000",
        "underlying_symbol": "KTOS",
        "option_side": "call",
        "expiration_date": date(2026, 9, 18),
        "strike": D("65"),
    }


def _share_execution(
    key: str,
    occurred_at: datetime,
    side: str,
    quantity: Decimal,
    price: Decimal,
) -> dict[str, object]:
    return {
        "external_key": key,
        "occurred_at": occurred_at,
        "side": side,
        "position_effect": "opening",
        "quantity": quantity,
        "price": price,
        "asset_type": "equity",
        "symbol": "KTOS",
    }
