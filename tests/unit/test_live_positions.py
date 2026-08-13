from datetime import UTC, date, datetime
from decimal import Decimal

from schwab_dashboard.application.dashboard.calculations import summarize_portfolio
from schwab_dashboard.application.dashboard.live_positions import build_live_position_book
from schwab_dashboard.application.dashboard.models import PositionSummary

D = Decimal


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
    assert summary.day_profit_loss_percent == D("4.166666666666666666666666667")


def test_portfolio_prefers_account_day_change_over_contradictory_position_pl() -> None:
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

    assert summary.day_profit_loss == D("-163.80")
    assert summary.day_profit_loss_percent == D("-163.80") / D("103853.77") * D("100")


def test_portfolio_excludes_same_day_deposit_from_daily_profit() -> None:
    summary = summarize_portfolio(
        (_position(day_profit_loss=D("3000")),),
        (
            {
                "liquidation_value": D("128000"),
                "initial_liquidation_value": D("100000"),
            },
        ),
        cash_movements=(
            {
                "occurred_at": date(2026, 8, 12),
                "movement_type": "transfer",
                "amount": D("25000"),
            },
        ),
        as_of=date(2026, 8, 12),
    )

    assert summary.day_external_cash_flow == D("25000")
    assert summary.day_profit_loss == D("3000")
    assert summary.day_profit_loss_percent == D("3")


def test_portfolio_excludes_deposit_when_utc_midnight_crosses_market_day() -> None:
    summary = summarize_portfolio(
        (_position(day_profit_loss=D("-219.03")),),
        (
            {
                "liquidation_value": D("131586.73"),
                "initial_liquidation_value": D("106805.76"),
            },
        ),
        cash_movements=(
            {
                # 2:08 PM New York on Aug 12. SQLite returns normalized UTC
                # datetimes without their original offset.
                "occurred_at": datetime(2026, 8, 12, 18, 8, 21),
                "movement_type": "transfer",
                "amount": D("25000"),
            },
        ),
        # 10:00 PM New York on Aug 12, despite the Aug 13 UTC date.
        as_of=datetime(2026, 8, 13, 2, 0, tzinfo=UTC),
    )

    assert summary.day_external_cash_flow == D("25000")
    assert summary.day_profit_loss == D("-219.03")
    assert summary.day_profit_loss_percent == D("-219.03") / D("106805.76") * D("100")


def test_portfolio_carries_prior_day_deposit_while_schwab_baseline_is_stale() -> None:
    summary = summarize_portfolio(
        (_position(day_profit_loss=D("-219.03")),),
        (
            {
                "liquidation_value": D("131586.73"),
                "initial_liquidation_value": D("106805.76"),
            },
        ),
        cash_movements=(
            {
                "occurred_at": datetime(2026, 8, 12, 18, 8, 21),
                "movement_type": "transfer",
                "amount": D("25000"),
            },
        ),
        as_of=date(2026, 8, 13),
    )

    assert summary.day_external_cash_flow == D("25000")
    assert summary.day_profit_loss == D("-219.03")


def test_portfolio_stops_carrying_deposit_after_schwab_baseline_advances() -> None:
    summary = summarize_portfolio(
        (_position(day_profit_loss=D("-219.03")),),
        (
            {
                "liquidation_value": D("131586.73"),
                "initial_liquidation_value": D("131805.76"),
            },
        ),
        cash_movements=(
            {
                "occurred_at": datetime(2026, 8, 12, 18, 8, 21),
                "movement_type": "transfer",
                "amount": D("25000"),
            },
        ),
        as_of=date(2026, 8, 13),
    )

    assert summary.day_external_cash_flow == D("0")
    assert summary.day_profit_loss == D("-219.03")


def test_portfolio_excludes_same_day_withdrawal_but_not_dividend() -> None:
    summary = summarize_portfolio(
        (_position(day_profit_loss=D("3100")),),
        (
            {
                "liquidation_value": D("78100"),
                "initial_liquidation_value": D("100000"),
            },
        ),
        cash_movements=(
            {
                "occurred_at": date(2026, 8, 12),
                "movement_type": "transfer",
                "amount": D("-25000"),
            },
            {
                "occurred_at": date(2026, 8, 12),
                "movement_type": "dividend",
                "amount": D("100"),
            },
        ),
        as_of=date(2026, 8, 12),
    )

    assert summary.day_external_cash_flow == D("-25000")
    assert summary.day_profit_loss == D("3100")
    assert summary.day_profit_loss_percent == D("3.1")


def test_portfolio_does_not_exclude_transfer_from_another_day() -> None:
    summary = summarize_portfolio(
        (_position(day_profit_loss=D("1000")),),
        (
            {
                "liquidation_value": D("101000"),
                "initial_liquidation_value": D("100000"),
            },
        ),
        cash_movements=(
            {
                "occurred_at": date(2026, 8, 11),
                "movement_type": "transfer",
                "amount": D("25000"),
            },
        ),
        as_of=date(2026, 8, 12),
    )

    assert summary.day_external_cash_flow == D("0")
    assert summary.day_profit_loss == D("1000")


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
