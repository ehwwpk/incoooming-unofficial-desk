from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from schwab_dashboard.application.dashboard.covered_calls import PricePoint
from schwab_dashboard.application.dashboard.live_option_clocks import build_open_call_clocks
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
    same_strike_later = {
        "symbol": "KTOS  261016C00065000",
        "underlying_symbol": "KTOS",
        "option_side": "call",
        "expiration_date": date(2026, 10, 16),
        "strike": D("65"),
        "bid": D("2.60"),
        "ask": D("2.80"),
        "quote_quality": "complete",
    }
    option_market = (quote, replacement_quote, same_strike_later)
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
    assert all(
        item.strike > D("65")
        for item in underlying.open_call_clocks[0].roll_quote_candidates
    )
    assert underlying.open_call_clocks[0].position_delta_share_equivalent == D("-60")
    assert underlying.open_call_clocks[0].position_gamma_delta_change_per_dollar == D("-4")
    assert underlying.open_call_clocks[0].position_vega_per_volatility_point == D("-10")
    assert underlying.open_call_theta_per_day == D("20.00")
    assert underlying.daily_price_change_percent == D("1.7")
    assert underlying.weekly_price_change_percent == D("20")
    live_quote_book = replace(
        book,
        underlyings=(
            replace(
                book.underlyings[0],
                current_price=D("61"),
                current_session_change_percent=D("2.5"),
            ),
        ),
    )
    live_quote_result = build_live_underlying_stats(
        live_book=live_quote_book,
        positions=(stock, call),
        executions=executions,
        cash_movements=(),
        lifecycle_events=(),
        daily_bars=bars,
        option_market=option_market,
        as_of=as_of,
    )
    assert live_quote_result[0].current_price == D("61")
    assert live_quote_result[0].daily_price_change_percent == D("2.5")
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


def test_live_card_keeps_the_campaign_that_still_owns_an_identical_contract() -> None:
    """An aggregated Aug $90 line must not inherit the campaign that rolled away.

    Two independently opened Aug $90 calls are fungible at the broker. The
    older one is closed and rolled into a Nov $75 call; the later Aug $90 call
    remains open. FIFO reconciliation is inferred, but the live card still
    needs to point at the surviving campaign instead of the latest broker order
    id or the already-rolled campaign.
    """

    as_of = date(2026, 8, 15)
    aug_90 = "KTOS  260821C00090000"
    stock = _position()
    live_call = _position(
        symbol=aug_90,
        description="KTOS AUG 21 2026 90 Call",
        asset_type="OPTION",
        quantity=D("-1"),
        average_price=D("1.14"),
        mark=D("0.10"),
        market_value=D("-10"),
        open_profit_loss=D("104"),
        underlying_symbol="KTOS",
        option_type="CALL",
        expiration_date=date(2026, 8, 21),
        strike=D("90"),
    )
    book = build_live_position_book((stock, live_call), as_of=as_of)

    def execution(
        key: str,
        order: str,
        symbol: str,
        occurred_at: datetime,
        side: str,
        effect: str,
        cash: str,
    ) -> dict[str, object]:
        return {
            "external_key": key,
            "order_external_key": order,
            "occurred_at": occurred_at,
            "side": side,
            "position_effect": effect,
            "quantity": D("1"),
            "price": abs(D(cash)) / D("100"),
            "net_cash": D(cash),
            "asset_type": "option",
            "symbol": symbol,
            "underlying_symbol": "KTOS",
            "option_side": "call",
        }

    jun_85 = "KTOS  260618C00085000"
    jun_70 = "KTOS  260618C00070000"
    nov_75 = "KTOS  261120C00075000"
    executions = (
        execution(
            "campaign-a-open",
            "campaign-a-open",
            jun_85,
            datetime(2026, 5, 29, 15, tzinfo=UTC),
            "sell",
            "opening",
            "56",
        ),
        execution(
            "campaign-b-open",
            "campaign-b-open",
            jun_70,
            datetime(2026, 6, 8, 15, tzinfo=UTC),
            "sell",
            "opening",
            "27",
        ),
        execution(
            "campaign-a-close-85",
            "campaign-a-roll-90",
            jun_85,
            datetime(2026, 6, 11, 15, tzinfo=UTC),
            "buy",
            "closing",
            "-5",
        ),
        execution(
            "campaign-a-open-90",
            "campaign-a-roll-90",
            aug_90,
            datetime(2026, 6, 11, 15, 1, tzinfo=UTC),
            "sell",
            "opening",
            "150",
        ),
        execution(
            "campaign-b-close-70",
            "campaign-b-roll-90",
            jun_70,
            datetime(2026, 6, 15, 15, tzinfo=UTC),
            "buy",
            "closing",
            "-4",
        ),
        execution(
            "campaign-b-open-90",
            "campaign-b-roll-90",
            aug_90,
            datetime(2026, 6, 15, 15, 1, tzinfo=UTC),
            "sell",
            "opening",
            "113",
        ),
        execution(
            "campaign-a-close-90",
            "campaign-a-roll-75",
            aug_90,
            datetime(2026, 6, 23, 15, tzinfo=UTC),
            "buy",
            "closing",
            "-46",
        ),
        execution(
            "campaign-a-open-75",
            "campaign-a-roll-75",
            nov_75,
            datetime(2026, 6, 23, 15, 1, tzinfo=UTC),
            "sell",
            "opening",
            "393",
        ),
    )

    clocks = build_open_call_clocks(
        "KTOS",
        book.calls,
        executions=executions,
        daily_bars=(),
        as_of=as_of,
    )

    assert len(clocks) == 1
    assert clocks[0].campaign_id == "campaign-b-open"
    assert clocks[0].campaign_label == "C2"


def test_put_print_moves_name_option_cash_and_apr_without_touching_dividends() -> None:
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
    book = build_live_position_book((stock, call), as_of=as_of)
    executions = (
        {
            "external_key": "put-sale",
            "occurred_at": datetime(2026, 8, 8, 15, tzinfo=UTC),
            "side": "sell",
            "position_effect": "opening",
            "quantity": D("1"),
            "gross_amount": D("120"),
            "net_cash": D("120"),
            "asset_type": "option",
            "symbol": "KTOS  260821P00060000",
            "underlying_symbol": "KTOS",
            "option_side": "put",
            "expiration_date": date(2026, 8, 21),
            "strike": D("60"),
        },
    )
    bars = tuple(
        {
            "symbol": "KTOS",
            "trade_date": as_of - timedelta(days=5 - index),
            "close": D("60"),
            "open": D("60"),
            "high": D("61"),
            "low": D("59"),
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
        as_of=as_of,
    )
    window = result[0].performance_windows[0]
    assert window.option_cash == D("120")
    assert window.option_apr > D("0")
    assert window.dividends == D("0")
    assert window.premium_capture_percent == D("100")


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
