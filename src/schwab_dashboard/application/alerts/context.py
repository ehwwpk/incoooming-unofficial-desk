from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from schwab_dashboard.application.dashboard.covered_calls import (
    OpenCallClock,
    UnderlyingCallStats,
)

D = Decimal
ZERO = D("0")
HUNDRED = D("100")


@dataclass(frozen=True, slots=True)
class ReviewPressure:
    """Transparent review heuristic; deliberately not a probability or trade signal."""

    score: int
    label: str
    strike_proximity_points: Decimal
    momentum_points: Decimal
    time_urgency_points: Decimal
    mark_expansion_points: Decimal
    primary_drivers: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CallReviewContext:
    call: OpenCallClock
    strike_distance_per_share: Decimal
    strike_distance_percent: Decimal
    covered_share_distance: Decimal
    mark_to_credit_ratio: Decimal
    pressure: ReviewPressure


@dataclass(frozen=True, slots=True)
class DividendReviewContext:
    call: OpenCallClock
    days_until_ex_dividend: int
    crossing_contracts: int
    strike_distance_per_share: Decimal
    strike_distance_percent: Decimal
    pre_dividend_gray_line: Decimal
    distance_to_gray_line_per_share: Decimal
    distance_to_gray_line_percent: Decimal
    extrinsic_per_share: Decimal
    dividend_to_extrinsic_ratio: Decimal | None
    is_in_the_money: bool
    dividend_exceeds_time_value: bool
    early_assignment_sensitive: bool


def build_call_review_context(
    underlying: UnderlyingCallStats,
    *,
    five_session_move_percent: Decimal,
) -> CallReviewContext:
    call = min(
        underlying.open_call_clocks,
        key=lambda item: abs(item.strike - underlying.current_price),
    )
    distance = call.strike - underlying.current_price
    distance_percent = _percent(distance, underlying.current_price)
    mark_to_credit = (
        call.mark_per_share / call.entry_credit_per_share
        if call.entry_credit_per_share > ZERO
        else ZERO
    )

    proximity_points = _clamp(
        (D("15") - max(distance_percent, ZERO)) / D("15") * D("40"),
        ZERO,
        D("40"),
    )
    momentum_points = _clamp(
        max(five_session_move_percent, ZERO) / D("25") * D("30"),
        ZERO,
        D("30"),
    )
    time_urgency_points = _clamp(
        (D("30") - D(call.days_to_expiration)) / D("30") * D("20"),
        ZERO,
        D("20"),
    )
    mark_expansion_points = _clamp(
        (mark_to_credit - D("1")) * D("10"),
        ZERO,
        D("10"),
    )
    components = (
        ("strike proximity", proximity_points),
        ("recent move", momentum_points),
        ("time left", time_urgency_points),
        ("option mark versus entry credit", mark_expansion_points),
    )
    score = int(
        sum((points for _, points in components), ZERO).quantize(
            D("1"), rounding=ROUND_HALF_UP
        )
    )
    primary_drivers = tuple(
        name
        for name, points in sorted(components, key=lambda item: item[1], reverse=True)
        if points > ZERO
    )[:2]

    return CallReviewContext(
        call=call,
        strike_distance_per_share=distance,
        strike_distance_percent=distance_percent,
        covered_share_distance=abs(distance) * D(call.contracts * 100),
        mark_to_credit_ratio=mark_to_credit,
        pressure=ReviewPressure(
            score=score,
            label=_pressure_label(score),
            strike_proximity_points=proximity_points,
            momentum_points=momentum_points,
            time_urgency_points=time_urgency_points,
            mark_expansion_points=mark_expansion_points,
            primary_drivers=primary_drivers,
        ),
    )


def build_dividend_review_context(
    underlying: UnderlyingCallStats,
    *,
    crossing_calls: Sequence[OpenCallClock],
    as_of: date,
) -> DividendReviewContext:
    ex_date = underlying.next_ex_dividend_date
    if ex_date is None:
        raise ValueError("Dividend review context requires an ex-dividend date")
    if not crossing_calls:
        raise ValueError("Dividend review context requires at least one crossing call")

    call = min(crossing_calls, key=lambda item: abs(item.strike - underlying.current_price))
    distance = call.strike - underlying.current_price
    gray_line = call.strike + underlying.dividend_per_share
    gray_distance = gray_line - underlying.current_price
    contract_shares = call.contracts * 100
    extrinsic_per_share = (
        call.remaining_extrinsic_value / D(contract_shares) if contract_shares else ZERO
    )
    ratio = (
        underlying.dividend_per_share / extrinsic_per_share
        if extrinsic_per_share > ZERO
        else None
    )
    is_in_the_money = underlying.current_price > call.strike
    dividend_exceeds_time_value = underlying.dividend_per_share > extrinsic_per_share

    return DividendReviewContext(
        call=call,
        days_until_ex_dividend=(ex_date - as_of).days,
        crossing_contracts=sum(item.contracts for item in crossing_calls),
        strike_distance_per_share=distance,
        strike_distance_percent=_percent(distance, underlying.current_price),
        pre_dividend_gray_line=gray_line,
        distance_to_gray_line_per_share=gray_distance,
        distance_to_gray_line_percent=_percent(gray_distance, underlying.current_price),
        extrinsic_per_share=extrinsic_per_share,
        dividend_to_extrinsic_ratio=ratio,
        is_in_the_money=is_in_the_money,
        dividend_exceeds_time_value=dividend_exceeds_time_value,
        early_assignment_sensitive=is_in_the_money and dividend_exceeds_time_value,
    )


def _percent(value: Decimal, base: Decimal) -> Decimal:
    return value / base * HUNDRED if base else ZERO


def _clamp(value: Decimal, lower: Decimal, upper: Decimal) -> Decimal:
    return min(max(value, lower), upper)


def _pressure_label(score: int) -> str:
    if score >= 75:
        return "HIGH"
    if score >= 50:
        return "ELEVATED"
    if score >= 25:
        return "MODERATE"
    return "LOW"
