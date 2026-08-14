from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from schwab_dashboard.application.dashboard.covered_calls import PricePoint
from schwab_dashboard.application.dashboard.live_positions import build_live_position_book
from schwab_dashboard.application.dashboard.live_underlying_stats import (
    _current_price_change,
    build_live_underlying_stats,
)
from schwab_dashboard.application.dashboard.models import PositionSummary

D = Decimal


def test_current_price_change_uses_the_correct_session_baseline() -> None:
    as_of = date(2026, 8, 10)
    points = tuple(
        PricePoint(
            date=as_of - timedelta(days=5 - index),
            label="",
            price=D(str(50 + index * 2)),
            x_percent=D("0"),
            y_percent=D("0"),
            is_friday=False,
        )
        for index in range(6)
    )

    assert _current_price_change(
        points,
        current_price=D("60"),
        sessions=5,
        as_of=as_of,
    ) == D("20")
    assert _current_price_change(
        points[:-1],
        current_price=D("60"),
        sessions=5,
        as_of=as_of,
    ) == (D("60") / D("50") - D("1")) * D("100")


def test_live_underlying_projection_restores_chart_clocks_and_theta() -> None:
    as_of = date(2026, 8, 10)
    stock = _position()
    call = _position(
        symbol="KTOS  260918C00065000",
        description="KTOS SEP 18 2026 65 Call",
        asset_type="OPTION",
        quantity=D("-2"),
        average_price=D("2.00"),
        mark=D("2.50"),
        market_value=D("-500"),
        open_profit_loss=D("-100"),
        underlying_symbol="KTOS",
        option_type="CALL",
        expiration_date=date(2026, 9, 18),
        strike=D("65"),
    )
    quote = {
        "symbol": call.symbol,
        "mark": D("2.50"),
        "bid": D("2.40"),
        "ask": D("2.60"),
        "implied_volatility": D("55"),
        "delta": D("0.30"),
        "gamma": D("0.02"),
        "theta": D("-0.10"),
        "vega": D("0.05"),
        "observed_at": datetime(2026, 8, 10, 20, tzinfo=UTC),
        "quote_quality": "live",
    }
    replacement_quote = {
        "symbol": "KTOS  260925C00070000",
        "underlying_symbol": "KTOS",
        "option_side": "call",
        "expiration_date": date(2026, 9, 25),
        "strike": D("70"),
        "bid": D("2.55"),
        "ask": D("2.75"),
        "quote_quality": "complete",
    }
    option_market = (quote, replacement_quote)
    book = build_live_position_book((stock, call), as_of=as_of, option_market=option_market)
    sold_at = datetime(2026, 8, 5, 15, tzinfo=UTC)
    executions = (
        {
            "external_key": "call-sale",
            "order_external_key": "order-1",
            "occurred_at": sold_at,
            "side": "sell",
            "position_effect": "opening",
            "quantity": D("2"),
            "price": D("2"),
            "gross_amount": D("400"),
            "net_cash": D("399"),
            "asset_type": "option",
            "symbol": call.symbol,
            "underlying_symbol": "KTOS",
            "option_side": "call",
            "expiration_date": date(2026, 9, 18),
            "strike": D("65"),
        },
        {
            "external_key": "stock-buy",
            "occurred_at": sold_at,
            "side": "buy",
            "position_effect": "opening",
            "quantity": D("100"),
            "price": D("50"),
            "asset_type": "equity",
            "symbol": "KTOS",
        },
    )
    bars = tuple(
        {
            "symbol": "KTOS",
            "trade_date": as_of - timedelta(days=5 - index),
            "close": D(str(50 + index * 2)),
            "open": D(str(49 + index * 2)),
            "high": D(str(51 + index * 2)),
            "low": D(str(48 + index * 2)),
            "volume": 1000,
        }
        for index in range(6)
    )

    result = build_live_underlying_stats(
        live_book=book,
        positions=(stock, call),
        executions=executions,
        cash_movements=(),
        lifecycle_events=(),
        daily_bars=bars,
        option_market=option_market,
        as_of=as_of,
    )

    assert len(result) == 1
    underlying = result[0]
    assert len(underlying.price_points) == 6
    assert len(underlying.open_call_clocks) == 1
    assert underlying.open_call_clocks[0].sold_on == sold_at.date()
    assert underlying.open_call_clocks[0].roll_quote_candidates[0].strike == D("70")
    assert underlying.open_call_theta_per_day == D("20.00")
    assert underlying.daily_price_change_percent == D("1.7")
    assert underlying.weekly_price_change_percent == D("20")
    fallback = replace(
        underlying,
        current_session_change_percent=None,
        current_week_change_percent=None,
    )
    assert fallback.daily_price_change_percent == (D("60") / D("58") - D("1")) * D("100")
    assert fallback.weekly_price_change_percent == D("20")
    short_history = replace(
        underlying,
        price_points=underlying.price_points[:1],
        current_session_change_percent=None,
        current_week_change_percent=None,
    )
    assert short_history.daily_price_change_percent is None
    assert short_history.weekly_price_change_percent is None
    assert [event.event_type for event in underlying.price_events] == ["sale"]
    assert len(underlying.share_trade_events) == 1
    assert underlying.performance_windows[0].option_cash == D("399")


def _position(**overrides: object) -> PositionSummary:
    values: dict[str, object] = {
        "account_mask": "...1234",
        "symbol": "KTOS",
        "description": "Kratos Defense",
        "asset_type": "EQUITY",
        "quantity": D("800"),
        "average_price": D("40"),
        "mark": D("60"),
        "market_value": D("48000"),
        "day_profit_loss": D("800"),
        "day_profit_loss_percent": D("1.7"),
        "strategy": None,
    }
    values.update(overrides)
    return PositionSummary(**values)  # type: ignore[arg-type]
