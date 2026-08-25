from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from schwab_dashboard.application.dashboard.calculations import summarize_portfolio
from schwab_dashboard.application.dashboard.live_positions import build_live_position_book
from schwab_dashboard.application.dashboard.models import (
    LiveUnderlyingPosition,
    PositionSummary,
)
from schwab_dashboard.application.expiration import ExpirationExpectation
from schwab_dashboard.application.market_time import OptionSessionState, QuoteSession

D = Decimal
PACIFIC = ZoneInfo("America/Los_Angeles")


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


def test_live_book_matches_short_calls_to_long_shares() -> None:
    stock = _position()
    call = _position(
        symbol="KTOS  260918C00075000",
        description="KTOS SEP 18 2026 75 Call",
        asset_type="OPTION",
        quantity=D("-5"),
        average_price=D("2.45"),
        mark=D("3.30"),
        market_value=D("-1650"),
        day_profit_loss=D("-100"),
        strategy="Short call",
        underlying_symbol="KTOS",
        option_type="CALL",
        expiration_date=date(2026, 9, 18),
        strike=D("75"),
        open_profit_loss=D("-425"),
    )

    book = build_live_position_book((stock, call), as_of=date(2026, 8, 10))

    assert book.open_call_positions == 1
    assert book.open_call_contracts == 5
    assert book.contract_capacity == 8
    assert book.covered_contracts == 5
    assert book.coverage_percent == D("62.500")
    assert book.open_mark_profit_loss == D("-425")
    assert book.calls[0].days_to_expiration == 39
    assert book.calls[0].strike_distance_per_share == D("15")
    assert book.calls[0].strike_distance_percent == D("25.00")


def test_live_book_prefers_market_quote_over_stale_account_position_mark() -> None:
    stock = _position(
        symbol="CVX",
        description="Chevron",
        mark=D("197.70"),
        market_value=D("158160"),
        day_profit_loss=D("0"),
        day_profit_loss_percent=D("0"),
    )
    call = _position(
        symbol="CVX   260918C00205000",
        asset_type="OPTION",
        quantity=D("-1"),
        underlying_symbol="CVX",
        option_type="CALL",
        expiration_date=date(2026, 9, 18),
        strike=D("205"),
    )
    observed_at = datetime(2026, 8, 14, 16, 34, 10, tzinfo=UTC)

    book = build_live_position_book(
        (stock, call),
        as_of=date(2026, 8, 14),
        underlying_market=(
            {
                "symbol": "CVX",
                "mark": D("200.80"),
                "previous_close": D("197.70"),
                "observed_at": observed_at,
                "quote_quality": "complete",
            },
        ),
    )

    underlying = book.underlyings[0]
    assert underlying.current_price == D("200.80")
    assert underlying.previous_close == D("197.70")
    assert underlying.market_value == D("160640.00")
    assert underlying.day_profit_loss == D("2480.00")
    assert underlying.current_session_change_percent == (D("200.80") / D("197.70") - D("1")) * D(
        "100"
    )
    assert underlying.quote_observed_at == observed_at
    assert underlying.quote_quality == "complete"
    assert book.calls[0].underlying_price == D("200.80")
    assert book.calls[0].strike_distance_per_share == D("4.20")


def _quoted_book(
    *,
    observed_at: datetime | None,
    evaluated_at: datetime | None,
) -> LiveUnderlyingPosition:
    quote: dict[str, object] = {
        "symbol": "CVX",
        "mark": D("200.80"),
        "previous_close": D("200.80"),
        "quote_quality": "complete",
    }
    if observed_at is not None:
        quote["observed_at"] = observed_at
    book = build_live_position_book(
        (
            _position(symbol="CVX", description="Chevron", mark=D("200.80")),
            _position(
                symbol="CVX   260918C00205000",
                asset_type="OPTION",
                quantity=D("-1"),
                underlying_symbol="CVX",
                option_type="CALL",
                expiration_date=date(2026, 9, 18),
                strike=D("205"),
            ),
        ),
        as_of=date(2026, 8, 14),
        evaluated_at=evaluated_at,
        underlying_market=(quote,),
    )
    return book.underlyings[0]


def test_monday_reader_sees_a_friday_print_labelled_as_prior_session() -> None:
    """Reproduces the live incident: sync succeeds, tape is still Friday's."""

    underlying = _quoted_book(
        observed_at=datetime(2026, 8, 14, 20, 0, tzinfo=UTC),
        evaluated_at=datetime(2026, 8, 17, 6, 40, tzinfo=PACIFIC),
    )

    assert underlying.quote_session is QuoteSession.PRIOR_SESSION
    assert underlying.is_prior_session_quote
    assert underlying.session_move_label == "FRI CLOSE"
    assert underlying.quote_stamp == "FRI 4:00 PM ET"


def test_quote_from_the_open_session_keeps_the_plain_day_caption() -> None:
    underlying = _quoted_book(
        observed_at=datetime(2026, 8, 17, 13, 31, tzinfo=UTC),
        evaluated_at=datetime(2026, 8, 17, 6, 40, tzinfo=PACIFIC),
    )

    assert underlying.quote_session is QuoteSession.CURRENT_SESSION
    assert underlying.is_prior_session_quote is False
    assert underlying.session_move_label == "DAY"


def test_book_without_broker_quote_times_claims_no_session_at_all() -> None:
    """CSV imports and demo fixtures must not be handed a fabricated clock."""

    underlying = _quoted_book(observed_at=None, evaluated_at=None)

    assert underlying.quote_session is QuoteSession.UNKNOWN
    assert underlying.is_prior_session_quote is False
    assert underlying.quote_stamp is None
    assert underlying.session_move_label == "DAY"


def test_portfolio_uses_liquidation_value_not_gross_positions() -> None:
    stock = _position(market_value=D("220000"), day_profit_loss=D("7000"))
    summary = summarize_portfolio(
        (stock,),
        (
            {
                "liquidation_value": D("175000"),
                "equity": D("175000"),
                "margin_balance": D("-45000"),
                "buying_power": D("30000"),
            },
        ),
    )

    assert summary.total_value == D("175000")
    assert summary.liquidation_value == D("175000")
    assert summary.gross_position_value == D("220000")
    assert summary.margin_balance == D("-45000")
    assert summary.day_profit_loss == D("7000")
    assert summary.day_profit_loss_percent == D("7000") / D("168000") * D("100")


def test_portfolio_uses_position_tape_when_account_nl_change_disagrees() -> None:
    stock = _position(market_value=D("62420"), day_profit_loss=D("-10904.37"))
    summary = summarize_portfolio(
        (stock,),
        (
            {
                "liquidation_value": D("103689.97"),
                "initial_liquidation_value": D("103853.77"),
            },
        ),
    )

    assert summary.day_profit_loss == D("-10904.37")
    assert summary.day_profit_loss_percent == D("-10904.37") / (
        D("103689.97") - D("-10904.37")
    ) * D("100")


def test_portfolio_sums_every_asset_type_on_the_broker_tape() -> None:
    summary = summarize_portfolio(
        (
            _position(symbol="CVX", day_profit_loss=D("1080.25")),
            _position(
                symbol="URNM",
                asset_type="COLLECTIVE_INVESTMENT",
                day_profit_loss=D("1155"),
            ),
            _position(
                symbol="CVX   260821C00210000",
                asset_type="OPTION",
                quantity=D("-1"),
                day_profit_loss=D("-4.50"),
            ),
            _position(
                symbol="T  4.5 2030",
                asset_type="FIXED_INCOME",
                day_profit_loss=D("12.00"),
            ),
            _position(
                symbol="USD",
                asset_type="CURRENCY",
                day_profit_loss=D("0"),
            ),
        ),
        ({"liquidation_value": D("135797.61")},),
    )

    assert summary.day_profit_loss == D("2242.75")
    assert summary.day_profit_loss_percent == D("2242.75") / (D("135797.61") - D("2242.75")) * D(
        "100"
    )


def test_portfolio_day_pl_ignores_deposits_and_stale_bod_nl() -> None:
    summary = summarize_portfolio(
        (_position(day_profit_loss=D("3000")),),
        (
            {
                "liquidation_value": D("128000"),
                "initial_liquidation_value": D("100000"),
            },
        ),
    )

    assert summary.day_external_cash_flow == D("0")
    assert summary.day_profit_loss == D("3000")
    assert summary.day_profit_loss_percent == D("3000") / D("125000") * D("100")


def test_portfolio_day_pl_is_blank_when_every_position_lacks_a_print() -> None:
    summary = summarize_portfolio(
        (
            _position(day_profit_loss=None),
            _position(symbol="CVX  260918C00220000", asset_type="OPTION", day_profit_loss=None),
        ),
        ({"liquidation_value": D("100000")},),
    )

    assert summary.day_profit_loss is None
    assert summary.day_profit_loss_percent is None


def test_portfolio_refuses_partial_open_position_day_pl() -> None:
    summary = summarize_portfolio(
        (
            _position(day_profit_loss=D("100")),
            _position(symbol="CASH", asset_type="CASH", day_profit_loss=None),
        ),
        ({"liquidation_value": D("100000")},),
    )

    assert summary.day_profit_loss is None
    assert summary.day_profit_loss_percent is None
    assert summary.open_position_day_profit_loss is None


def test_portfolio_day_pl_does_not_follow_the_readers_calendar() -> None:
    summary = summarize_portfolio(
        (_position(day_profit_loss=D("1258.60")),),
        ({"liquidation_value": D("136057.17")},),
    )

    assert summary.day_profit_loss == D("1258.60")
    assert summary.day_profit_loss_percent == D("1258.60") / (D("136057.17") - D("1258.60")) * D(
        "100"
    )


def test_portfolio_empty_book_is_a_flat_session_not_a_blank() -> None:
    summary = summarize_portfolio((), ({"liquidation_value": D("1000")},))

    assert summary.day_profit_loss == D("0")
    assert summary.day_profit_loss_percent == D("0")


def test_portfolio_csv_book_uses_net_position_value_as_percent_denominator() -> None:
    stock = _position(market_value=D("50000"), day_profit_loss=D("1000"))
    option = _position(
        symbol="CVX   260918C00220000",
        asset_type="OPTION",
        market_value=D("-200"),
        day_profit_loss=D("40"),
    )
    summary = summarize_portfolio((stock, option))

    assert summary.liquidation_value is None
    assert summary.day_profit_loss == D("1040")
    assert summary.day_profit_loss_percent == D("1040") / D("48760") * D("100")


def test_portfolio_excludes_same_day_withdrawal_but_not_dividend() -> None:
    summary = summarize_portfolio(
        (_position(day_profit_loss=D("3100")),),
        (
            {
                "liquidation_value": D("78100"),
                "initial_liquidation_value": D("100000"),
            },
        ),
    )

    assert summary.day_external_cash_flow == D("0")
    assert summary.day_profit_loss == D("3100")
    assert summary.day_profit_loss_percent == D("3100") / D("75000") * D("100")


def test_short_puts_share_the_existing_underlying_group() -> None:
    stock = _position()
    call = _position(
        symbol="KTOS  260918C00075000",
        asset_type="OPTION",
        quantity=D("-2"),
        underlying_symbol="KTOS",
        option_type="CALL",
        expiration_date=date(2026, 9, 18),
        strike=D("75"),
    )
    put = _position(
        symbol="KTOS  260918P00050000",
        asset_type="OPTION",
        quantity=D("-1"),
        underlying_symbol="KTOS",
        option_type="PUT",
        expiration_date=date(2026, 9, 18),
        strike=D("50"),
    )

    book = build_live_position_book((stock, call, put), as_of=date(2026, 8, 10))

    assert len(book.underlyings) == 1
    assert book.open_call_contracts == 2
    assert book.open_put_contracts == 1
    assert book.underlyings[0].open_put_contracts == 1
    assert book.puts[0].strike_distance_per_share == D("10")
    assert book.total_open_mark_profit_loss == D("0")
    assert book.estimated_put_theta_per_day == D("0")


def test_short_put_clock_uses_the_oldest_remaining_open_lot_after_partial_close() -> None:
    stock = _position()
    put = _position(
        symbol="KTOS  260918P00050000",
        asset_type="OPTION",
        quantity=D("-1"),
        underlying_symbol="KTOS",
        option_type="PUT",
        expiration_date=date(2026, 9, 18),
        strike=D("50"),
    )
    executions = (
        {
            "symbol": put.symbol,
            "asset_type": "option",
            "side": "sell",
            "position_effect": "opening",
            "quantity": D("1"),
            "occurred_at": date(2026, 8, 1),
        },
        {
            "symbol": put.symbol,
            "asset_type": "option",
            "side": "sell",
            "position_effect": "opening",
            "quantity": D("1"),
            "occurred_at": date(2026, 8, 5),
        },
        {
            "symbol": put.symbol,
            "asset_type": "option",
            "side": "buy",
            "position_effect": "closing",
            "quantity": D("1"),
            "occurred_at": date(2026, 8, 8),
        },
    )

    book = build_live_position_book(
        (stock, put),
        as_of=date(2026, 8, 10),
        executions=executions,
    )

    assert book.puts[0].opened_on == date(2026, 8, 5)
    assert book.puts[0].original_days_to_expiration == 44


def test_option_theta_uses_exported_contract_multiplier() -> None:
    stock = _position(quantity=D("450"))
    call = _position(
        symbol="KTOS1 260918C00075000",
        asset_type="OPTION",
        quantity=D("-2"),
        underlying_symbol="KTOS",
        option_type="CALL",
        expiration_date=date(2026, 9, 18),
        strike=D("75"),
        contract_multiplier=D("150"),
        multiplier_source="exported",
    )
    book = build_live_position_book(
        (stock, call),
        as_of=date(2026, 8, 10),
        option_market=(({"symbol": call.symbol, "theta": D("-0.05")}),),
    )

    assert book.calls[0].contract_multiplier == D("150")
    assert book.contract_capacity == 3
    assert book.covered_contracts == 2
    assert book.underlyings[0].estimated_theta_per_day == D("15.00")


def test_expired_friday_inventory_stays_visible_but_loses_trading_actions() -> None:
    stock = _position()
    call = _position(
        symbol="KTOS  260814C00064000",
        asset_type="OPTION",
        quantity=D("-1"),
        average_price=D("0.30"),
        mark=D("0.10"),
        market_value=D("-10"),
        underlying_symbol="KTOS",
        option_type="CALL",
        expiration_date=date(2026, 8, 14),
        strike=D("64"),
    )
    put = _position(
        symbol="KTOS  260814P00060000",
        asset_type="OPTION",
        quantity=D("-1"),
        average_price=D("0.30"),
        mark=D("0.10"),
        market_value=D("-10"),
        underlying_symbol="KTOS",
        option_type="PUT",
        expiration_date=date(2026, 8, 14),
        strike=D("60"),
    )
    option_market = (
        {"symbol": call.symbol, "theta": D("-0.30")},
        {"symbol": put.symbol, "theta": D("-0.20")},
        {
            "symbol": "KTOS  260821C00068000",
            "underlying_symbol": "KTOS",
            "option_side": "CALL",
            "expiration_date": date(2026, 8, 21),
            "strike": D("68"),
            "bid": D("0.25"),
        },
        {
            "symbol": "KTOS  260821P00056000",
            "underlying_symbol": "KTOS",
            "option_side": "PUT",
            "expiration_date": date(2026, 8, 21),
            "strike": D("56"),
            "bid": D("0.20"),
        },
    )

    book = build_live_position_book(
        (stock, call, put),
        as_of=date(2026, 8, 14),
        evaluated_at=datetime(2026, 8, 14, 18, 28, tzinfo=PACIFIC),
        option_market=option_market,
        daily_bars=(
            {
                "symbol": "KTOS",
                "trade_date": date(2026, 8, 14),
                "close": D("63"),
            },
        ),
    )

    assert book.open_call_positions == 1
    assert book.open_put_positions == 1
    assert all(
        option.session_state is OptionSessionState.CLOSED_PENDING_SETTLEMENT
        for option in (*book.calls, *book.puts)
    )
    assert all(not option.can_close_or_roll for option in (*book.calls, *book.puts))
    assert all(not option.roll_quote_candidates for option in (*book.calls, *book.puts))
    assert all(
        option.expiration_assessment is not None
        and option.expiration_assessment.reference_is_official_close
        and option.expiration_assessment.expectation is ExpirationExpectation.EXPECTED_WORTHLESS
        for option in (*book.calls, *book.puts)
    )
    assert book.underlyings[0].estimated_theta_per_day == D("0")
    assert book.underlyings[0].estimated_put_theta_per_day == D("0")
