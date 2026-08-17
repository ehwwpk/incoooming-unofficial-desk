from decimal import Decimal

from schwab_dashboard.application.risk.price_time import (
    aggregate_price_time_reads,
    build_price_time_read,
)


def test_price_time_read_compares_gamma_adjusted_price_effect_with_theta() -> None:
    read = build_price_time_read(
        position_delta=Decimal("-25"),
        position_gamma=Decimal("-4"),
        theta_per_day=Decimal("10"),
        current_underlying_price=Decimal("101"),
        previous_close=Decimal("100"),
        weekly_reference_price=Decimal("95"),
    )

    assert read.price_effect == Decimal("-23.0")
    assert read.up_one_dollar_effect == Decimal("-27.0")
    assert read.down_one_dollar_effect == Decimal("23.0")
    assert read.price_plus_one_day == Decimal("-13.0")
    assert read.price_effect_in_theta_days == Decimal("2.3")
    assert read.consequence == "Price move cost about 2.3 days of theta."
    assert read.compact_consequence == "PRICE COST 2.3 THETA-DAYS"
    assert read.delta_pressure_change == Decimal("4")
    assert read.delta_pressure_label == "RISING"
    assert read.five_session_move_percent == Decimal("6") / Decimal("95") * Decimal("100")
    assert read.adverse_move_direction == "UP"
    assert read.pressure_trend_label == "BUILDING"
    assert read.absolute_pressure_change == Decimal("4")
    assert read.compact_pressure == "5D UP-MOVE RISK BUILDING"
    assert "$4" in read.pressure_summary
    assert "gamma" in read.gamma_note
    assert read.book_read == (
        "More contracts moved the wrong way this week. Current gamma makes the next adverse $1 "
        "matter more; the rows below show where."
    )


def test_price_time_read_marks_a_favorable_underlying_move_plainly() -> None:
    read = build_price_time_read(
        position_delta=Decimal("-25"),
        position_gamma=Decimal("-4"),
        theta_per_day=Decimal("10"),
        current_underlying_price=Decimal("99"),
        previous_close=Decimal("100"),
        weekly_reference_price=Decimal("102"),
    )

    assert read.price_effect == Decimal("27.0")
    assert read.up_one_dollar_effect == Decimal("-27.0")
    assert read.down_one_dollar_effect == Decimal("23.0")
    assert read.price_plus_one_day == Decimal("37.0")
    assert read.consequence == "Price and time both helped the short option."
    assert read.compact_consequence == "PRICE + TIME HELPED"
    assert read.delta_pressure_label == "EASING"
    assert read.delta_pressure_change == Decimal("-4")
    assert read.adverse_move_direction == "UP"
    assert read.compact_pressure == "5D UP-MOVE RISK EASING"


def test_price_time_read_handles_short_put_pressure_direction() -> None:
    read = build_price_time_read(
        position_delta=Decimal("25"),
        position_gamma=Decimal("-4"),
        theta_per_day=Decimal("8"),
        current_underlying_price=Decimal("99"),
        previous_close=Decimal("100"),
        weekly_reference_price=Decimal("104"),
    )

    assert read.price_effect == Decimal("-23.0")
    assert read.up_one_dollar_effect == Decimal("23.0")
    assert read.down_one_dollar_effect == Decimal("-27.0")
    assert read.delta_pressure_change == Decimal("4")
    assert read.delta_pressure_label == "RISING"
    assert read.adverse_move_direction == "DOWN"
    assert read.compact_pressure == "5D DOWN-MOVE RISK BUILDING"
    assert "steepen" in read.gamma_note


def test_price_time_read_keeps_missing_inputs_honest() -> None:
    read = build_price_time_read(
        position_delta=Decimal("-25"),
        position_gamma=None,
        theta_per_day=Decimal("10"),
        current_underlying_price=Decimal("101"),
        previous_close=None,
        weekly_reference_price=None,
    )

    assert read.price_effect is None
    assert read.up_one_dollar_effect == Decimal("-25")
    assert read.down_one_dollar_effect == Decimal("25")
    assert read.price_plus_one_day is None
    assert read.delta_pressure_label is None
    assert read.five_session_move_percent is None
    assert read.adverse_move_direction == "UP"
    assert read.model_coverage_percent == Decimal("33.33333333333333333333333333")
    assert read.consequence == "Price effect needs a current underlying move."


def test_price_time_reads_aggregate_signed_effects_and_time() -> None:
    first = build_price_time_read(
        position_delta=Decimal("-20"),
        position_gamma=Decimal("-2"),
        theta_per_day=Decimal("6"),
        current_underlying_price=Decimal("101"),
        previous_close=Decimal("100"),
        weekly_reference_price=Decimal("98"),
    )
    second = build_price_time_read(
        position_delta=Decimal("10"),
        position_gamma=Decimal("-1"),
        theta_per_day=Decimal("4"),
        current_underlying_price=Decimal("101"),
        previous_close=Decimal("100"),
        weekly_reference_price=Decimal("98"),
    )

    aggregate = aggregate_price_time_reads((first, second))

    assert aggregate is not None
    assert aggregate.price_effect == Decimal("-8.5")
    assert aggregate.up_one_dollar_effect == Decimal("-11.5")
    assert aggregate.down_one_dollar_effect == Decimal("8.5")
    assert aggregate.theta_per_day == Decimal("10")
    assert aggregate.price_plus_one_day == Decimal("1.5")
    assert aggregate.five_session_move_percent == Decimal("3") / Decimal("98") * Decimal("100")
    assert aggregate.adverse_move_direction is None
    assert aggregate.book_read == (
        "The book mostly held its ground this week. Time decay did more of the work; the rows "
        "below show where risk still sits."
    )


def test_book_read_keeps_missing_model_inputs_honest() -> None:
    read = build_price_time_read(
        position_delta=Decimal("-25"),
        position_gamma=None,
        theta_per_day=Decimal("10"),
        current_underlying_price=Decimal("101"),
        previous_close=None,
        weekly_reference_price=None,
    )

    assert read.book_read == (
        "The weekly pressure read is partial. The rows below keep missing model inputs blank "
        "instead of filling the gaps with guesses."
    )
