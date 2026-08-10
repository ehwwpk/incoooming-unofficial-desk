from dataclasses import replace
from decimal import Decimal

from schwab_dashboard.application.alerts.context import (
    build_call_review_context,
    build_dividend_review_context,
)
from schwab_dashboard.infrastructure.demo.dashboard import DemoDashboardReader

D = Decimal


def test_call_review_context_exposes_auditable_ktos_pressure() -> None:
    snapshot = DemoDashboardReader().execute()
    ktos = next(item for item in snapshot.underlyings if item.symbol == "KTOS")
    move = (ktos.current_price / ktos.price_points[-6].price - 1) * D("100")

    context = build_call_review_context(ktos, five_session_move_percent=move)

    assert context.call.strike == D("75")
    assert context.strike_distance_per_share == D("14.23")
    assert context.strike_distance_percent.quantize(D("0.1")) == D("23.4")
    assert context.covered_share_distance == D("7115.00")
    assert context.mark_to_credit_ratio.quantize(D("0.01")) == D("0.29")
    assert context.pressure.score == 36
    assert context.pressure.label == "MODERATE"
    assert context.pressure.momentum_points == D("30")
    assert context.pressure.time_urgency_points == D("6")
    assert context.pressure.primary_drivers == ("recent move", "time left")


def test_call_review_pressure_clamps_without_dividing_by_zero() -> None:
    snapshot = DemoDashboardReader().execute()
    ktos = next(item for item in snapshot.underlyings if item.symbol == "KTOS")
    call = replace(
        ktos.open_call_clocks[0],
        days_to_expiration=0,
        entry_credit_per_share=D("0"),
        mark_per_share=D("10"),
    )
    stressed = replace(ktos, current_price=D("100"), open_call_clocks=(call,))

    context = build_call_review_context(stressed, five_session_move_percent=D("50"))

    assert context.mark_to_credit_ratio == D("0")
    assert context.pressure.strike_proximity_points == D("40")
    assert context.pressure.momentum_points == D("30")
    assert context.pressure.time_urgency_points == D("20")
    assert context.pressure.mark_expansion_points == D("0")
    assert context.pressure.score == 90
    assert context.pressure.label == "HIGH"


def test_dividend_context_keeps_price_adjustment_and_assignment_logic_separate() -> None:
    snapshot = DemoDashboardReader().execute()
    cvx = next(item for item in snapshot.underlyings if item.symbol == "CVX")
    ex_date = cvx.next_ex_dividend_date
    assert ex_date is not None
    crossing_calls = tuple(call for call in cvx.open_call_clocks if call.expires_on >= ex_date)

    context = build_dividend_review_context(
        cvx,
        crossing_calls=crossing_calls,
        as_of=snapshot.as_of.date(),
    )

    assert context.call.strike == D("205")
    assert context.days_until_ex_dividend == 12
    assert context.crossing_contracts == 5
    assert context.strike_distance_per_share == D("18.44")
    assert context.pre_dividend_gray_line == D("206.78")
    assert context.distance_to_gray_line_per_share == D("20.22")
    assert context.distance_to_gray_line_percent.quantize(D("0.1")) == D("10.8")
    assert context.extrinsic_per_share == D("1.10")
    assert context.dividend_to_extrinsic_ratio is not None
    assert context.dividend_to_extrinsic_ratio.quantize(D("0.01")) == D("1.62")
    assert context.is_in_the_money is False
    assert context.early_assignment_sensitive is False


def test_zero_time_value_only_escalates_assignment_sensitivity_when_itm() -> None:
    snapshot = DemoDashboardReader().execute()
    cvx = next(item for item in snapshot.underlyings if item.symbol == "CVX")
    call = replace(cvx.open_call_clocks[1], remaining_extrinsic_value=D("0"))
    ex_date = cvx.next_ex_dividend_date
    assert ex_date is not None

    at_strike = build_dividend_review_context(
        replace(cvx, current_price=call.strike, open_call_clocks=(call,)),
        crossing_calls=(call,),
        as_of=snapshot.as_of.date(),
    )
    above_strike = build_dividend_review_context(
        replace(cvx, current_price=call.strike + D("0.01"), open_call_clocks=(call,)),
        crossing_calls=(call,),
        as_of=snapshot.as_of.date(),
    )

    assert at_strike.dividend_to_extrinsic_ratio is None
    assert at_strike.dividend_exceeds_time_value is True
    assert at_strike.early_assignment_sensitive is False
    assert above_strike.early_assignment_sensitive is True
