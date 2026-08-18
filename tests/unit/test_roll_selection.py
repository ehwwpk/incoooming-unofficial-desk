from datetime import date, timedelta
from decimal import Decimal

from schwab_dashboard.application.rolls import RollQuote, RollSource, select_roll_candidates
from schwab_dashboard.application.rolls.select import NEAREST_CASH_AND_TIME
from schwab_dashboard.domain.instruments import OptionSide

D = Decimal
EXPIRY = date(2026, 8, 14)


def test_roll_selection_uses_conservative_two_leg_cash_and_nearby_grid() -> None:
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

    assert [item.option_symbol for item in result.candidates] == ["flat", "fast"]
    assert result.candidates[0].net_roll_cash == D("0")
    assert result.candidates[0].highlight
    assert result.candidates[0].family_label == NEAREST_CASH_AND_TIME
    assert result.candidates[1].family_label == ""
    assert "LOWEST CASH COST" not in {item.family_label for item in result.candidates}
    assert "LEAST EXTRA TIME" not in {item.family_label for item in result.candidates}


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
        (_quote("replacement", days=7, strike="53", bid="1.25"),),
    )

    assert result.candidates[0].net_roll_cash == D("5.00")
    assert result.candidates[0].assignment_room_gain == D("60")


def test_roll_selection_rejects_same_strike_call_date_pushes() -> None:
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
            _quote("date-push", days=7, strike="68", bid="1.25"),
            _quote("up-and-out", days=21, strike="72.5", bid="1.20"),
        ),
    )

    assert [item.option_symbol for item in result.candidates] == ["up-and-out"]
    assert result.candidates[0].assignment_room_gain > 0


def test_roll_selection_explains_when_only_same_strike_calls_are_loaded() -> None:
    source = RollSource(
        symbol="CVX",
        option_symbol="CVX CALL",
        option_side=OptionSide.CALL,
        expires_on=EXPIRY,
        strike=D("200"),
        contracts=1,
        close_ask_per_share=D("1.50"),
        current_price=D("198"),
        quote_status="FRESH",
    )
    result = select_roll_candidates(
        source,
        (_quote("calendar", days=28, strike="200", bid="1.55"),),
    )

    assert result.candidates == ()
    assert result.no_clean_reason is not None
    assert "higher" in result.no_clean_reason


def test_roll_selection_keeps_the_nearest_listed_week_ahead_of_far_room() -> None:
    source = RollSource(
        symbol="URNM",
        option_symbol="URNM CALL",
        option_side=OptionSide.CALL,
        expires_on=EXPIRY,
        strike=D("70"),
        contracts=1,
        close_ask_per_share=D("1.00"),
        current_price=D("68"),
        quote_status="FRESH",
    )
    result = select_roll_candidates(
        source,
        (
            _quote("tiny-lift", days=7, strike="71", bid="1.00"),
            _quote("real-room", days=28, strike="80", bid="1.00"),
        ),
        limit=2,
    )

    assert [item.option_symbol for item in result.candidates] == ["tiny-lift"]
    assert result.candidates[0].highlight


def test_roll_selection_still_allows_same_strike_put_calendars() -> None:
    source = RollSource(
        symbol="XYZ",
        option_symbol="XYZ PUT",
        option_side=OptionSide.PUT,
        expires_on=EXPIRY,
        strike=D("50"),
        contracts=1,
        close_ask_per_share=D("1.00"),
        current_price=D("48"),
        quote_status="FRESH",
    )
    result = select_roll_candidates(
        source,
        (
            _quote("same-put", days=7, strike="50", bid="1.00"),
            _quote("down-and-out", days=14, strike="47", bid="1.00"),
        ),
    )

    assert [item.option_symbol for item in result.candidates] == ["same-put", "down-and-out"]


def test_cvx_nearby_grid_surfaces_the_215_weekly_as_dual_best() -> None:
    source = RollSource(
        symbol="CVX",
        option_symbol="CVX  260821C00210000",
        option_side=OptionSide.CALL,
        expires_on=date(2026, 8, 21),
        strike=D("210"),
        contracts=1,
        close_ask_per_share=D("0.32"),
        current_price=D("202.50"),
        quote_status="FRESH",
    )
    result = select_roll_candidates(
        source,
        (
            _dated("CVX  260828C00212500", date(2026, 8, 28), "212.50", "0.43"),
            _dated("CVX  260828C00215000", date(2026, 8, 28), "215", "0.25"),
            _dated("CVX  260828C00217500", date(2026, 8, 28), "217.50", "0.10"),
            _dated("CVX  260904C00212500", date(2026, 9, 4), "212.50", "0.80"),
            _dated("CVX  260904C00215000", date(2026, 9, 4), "215", "0.65"),
            _dated("CVX  260904C00217500", date(2026, 9, 4), "217.50", "0.40"),
            _dated("CVX  260911C00212500", date(2026, 9, 11), "212.50", "1.10"),
            _dated("CVX  260911C00215000", date(2026, 9, 11), "215", "0.90"),
            _dated("CVX  260911C00217500", date(2026, 9, 11), "217.50", "0.60"),
            _dated("CVX  260918C00220000", date(2026, 9, 18), "220", "0.96"),
        ),
    )

    symbols = [item.option_symbol for item in result.candidates]
    assert symbols[:3] == [
        "CVX  260828C00212500",
        "CVX  260828C00215000",
        "CVX  260828C00217500",
    ]
    assert "CVX  260918C00220000" not in symbols
    assert len(result.candidates) == 9
    highlighted = next(item for item in result.candidates if item.highlight)
    assert highlighted.option_symbol == "CVX  260828C00215000"
    assert highlighted.net_roll_cash == D("-7.00")
    assert highlighted.cost_label == "NEAR FLAT"
    assert highlighted.added_days == 7
    assert highlighted.family_label == NEAREST_CASH_AND_TIME
    assert highlighted.cash_per_extra_day == D("-1.00")


def test_nearby_grid_keeps_minimal_strike_moves_off_a_far_monthly() -> None:
    source = RollSource(
        symbol="CVX",
        option_symbol="CVX  260821C00210000",
        option_side=OptionSide.CALL,
        expires_on=date(2026, 8, 21),
        strike=D("210"),
        contracts=1,
        close_ask_per_share=D("0.32"),
        current_price=D("202.50"),
        quote_status="FRESH",
    )
    result = select_roll_candidates(
        source,
        (
            _dated("CVX  260828C00212500", date(2026, 8, 28), "212.50", "0.43"),
            _dated("CVX  260828C00215000", date(2026, 8, 28), "215", "0.25"),
            _dated("CVX  260828C00217500", date(2026, 8, 28), "217.50", "0.10"),
            _dated("CVX  260918C00220000", date(2026, 9, 18), "220", "1.55"),
            _dated("CVX  260918C00230000", date(2026, 9, 18), "230", "0.47"),
            _dated("CVX  260918C00240000", date(2026, 9, 18), "240", "0.70"),
            _dated("CVX  261002C00240000", date(2026, 10, 2), "240", "1.20"),
        ),
    )

    symbols = [item.option_symbol for item in result.candidates]
    assert symbols[:3] == [
        "CVX  260828C00212500",
        "CVX  260828C00215000",
        "CVX  260828C00217500",
    ]
    assert "CVX  260918C00220000" in symbols
    assert "CVX  260918C00230000" not in symbols
    assert "CVX  260918C00240000" not in symbols
    assert "CVX  261002C00240000" not in symbols
    highlighted = next(item for item in result.candidates if item.highlight)
    assert highlighted.option_symbol == "CVX  260828C00215000"


def test_roll_selection_skips_a_zero_bid_and_takes_the_next_listed_strike() -> None:
    source = RollSource(
        symbol="CVX",
        option_symbol="CVX CALL",
        option_side=OptionSide.CALL,
        expires_on=date(2026, 8, 21),
        strike=D("210"),
        contracts=1,
        close_ask_per_share=D("0.32"),
        current_price=D("202.50"),
        quote_status="FRESH",
    )
    result = select_roll_candidates(
        source,
        (
            _dated("dead-bid", date(2026, 8, 28), "212.50", "0"),
            _dated("next-listed", date(2026, 8, 28), "215", "0.25"),
            _dated("farther", date(2026, 8, 28), "217.50", "0.10"),
            _dated("third", date(2026, 8, 28), "220", "0.05"),
        ),
    )

    assert [item.option_symbol for item in result.candidates] == [
        "next-listed",
        "farther",
        "third",
    ]


def test_roll_selection_appends_a_preferred_target_outside_the_nearby_grid() -> None:
    source = RollSource(
        symbol="CVX",
        option_symbol="CVX CALL",
        option_side=OptionSide.CALL,
        expires_on=date(2026, 8, 21),
        strike=D("210"),
        contracts=1,
        close_ask_per_share=D("0.32"),
        current_price=D("202.50"),
        quote_status="FRESH",
    )
    result = select_roll_candidates(
        source,
        (
            _dated("near-a", date(2026, 8, 28), "215", "0.25"),
            _dated("near-b", date(2026, 8, 28), "217.50", "0.10"),
            _dated("near-c", date(2026, 8, 28), "220", "0.05"),
            _dated("preferred-far", date(2026, 10, 2), "240", "0.96"),
        ),
        preferred_option_symbol="preferred-far",
    )

    assert [item.option_symbol for item in result.candidates] == [
        "near-a",
        "near-b",
        "near-c",
        "preferred-far",
    ]


def test_two_quote_book_does_not_invent_a_least_extra_time_slogan() -> None:
    source = RollSource(
        symbol="CVX",
        option_symbol="CVX CALL",
        option_side=OptionSide.CALL,
        expires_on=date(2026, 8, 21),
        strike=D("210"),
        contracts=1,
        close_ask_per_share=D("0.32"),
        current_price=D("202.50"),
        quote_status="FRESH",
    )
    result = select_roll_candidates(
        source,
        (
            _dated("weekly", date(2026, 8, 28), "217.50", "0.10"),
            _dated("monthly", date(2026, 9, 18), "220", "0.96"),
        ),
    )

    assert [item.option_symbol for item in result.candidates] == ["weekly", "monthly"]
    assert all(item.family_label != "LEAST EXTRA TIME" for item in result.candidates)
    assert result.candidates[0].highlight


def _quote(symbol: str, *, days: int, strike: str, bid: str) -> RollQuote:
    return _dated(symbol, EXPIRY + timedelta(days=days), strike, bid)


def _dated(symbol: str, expires_on: date, strike: str, bid: str) -> RollQuote:
    return RollQuote(
        option_symbol=symbol,
        expires_on=expires_on,
        strike=D(strike),
        sell_bid_per_share=D(bid),
        quote_source="TEST",
        spread_percent=D("5"),
        open_interest=100,
        volume=10,
    )
