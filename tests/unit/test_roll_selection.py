from datetime import date, timedelta
from decimal import Decimal

from schwab_dashboard.application.rolls import RollQuote, RollSource, select_roll_candidates
from schwab_dashboard.domain.instruments import OptionSide

D = Decimal
EXPIRY = date(2026, 8, 14)


def test_roll_selection_uses_conservative_two_leg_cash_and_diversifies() -> None:
    source = RollSource(
        symbol="KTOS",
        option_symbol="KTOS CALL",
        option_side=OptionSide.CALL,
        expires_on=EXPIRY,
        strike=D("68"),
        contracts=2,
        close_ask_per_share=D("1.25"),
        current_price=D("67"),
        quote_status="FRESH",
    )
    result = select_roll_candidates(
        source,
        (
            _quote("flat", days=7, strike="70", bid="1.25"),
            _quote("fast", days=7, strike="72.5", bid="0.90"),
            _quote("room", days=35, strike="80", bid="0.75"),
        ),
    )

    assert len(result.candidates) == 3
    assert result.candidates[0].net_roll_cash == D("0")
    assert {item.family_label for item in result.candidates} == {
        "LOWEST CASH COST",
        "LEAST EXTRA TIME",
        "MOST STRIKE ROOM",
    }


def test_roll_selection_explains_when_chain_has_no_valid_replacement() -> None:
    source = RollSource(
        symbol="URNM",
        option_symbol="URNM PUT",
        option_side=OptionSide.PUT,
        expires_on=EXPIRY,
        strike=D("55"),
        contracts=1,
        close_ask_per_share=D("2"),
        current_price=D("54"),
        quote_status="FRESH",
    )
    result = select_roll_candidates(
        source,
        (_quote("wrong-way", days=7, strike="60", bid="3"),),
    )

    assert result.candidates == ()
    assert result.no_clean_reason is not None
    assert "same or lower" in result.no_clean_reason


def test_roll_cash_uses_the_actual_contract_multiplier() -> None:
    source = RollSource(
        symbol="ADJUSTED",
        option_symbol="ADJUSTED CALL",
        option_side=OptionSide.CALL,
        expires_on=EXPIRY,
        strike=D("50"),
        contracts=2,
        close_ask_per_share=D("1"),
        current_price=D("48"),
        quote_status="FRESH",
        contract_multiplier=D("10"),
    )

    result = select_roll_candidates(
        source,
        (_quote("replacement", days=7, strike="55", bid="1.25"),),
    )

    assert result.candidates[0].net_roll_cash == D("5.00")
    assert result.candidates[0].assignment_room_gain == D("100")


def _quote(symbol: str, *, days: int, strike: str, bid: str) -> RollQuote:
    return RollQuote(
        option_symbol=symbol,
        expires_on=EXPIRY + timedelta(days=days),
        strike=D(strike),
        sell_bid_per_share=D(bid),
        quote_source="TEST",
        spread_percent=D("5"),
        open_interest=100,
        volume=10,
    )
