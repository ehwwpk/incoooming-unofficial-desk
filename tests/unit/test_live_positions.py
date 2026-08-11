from datetime import date
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
