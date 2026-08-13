from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from schwab_dashboard.application.alerts.identity import option_alert_id
from schwab_dashboard.application.alerts.models import AlertFact, AlertLevel, DeskAlert
from schwab_dashboard.application.alerts.rolls import build_neutral_roll_scenarios
from schwab_dashboard.application.dashboard.covered_calls import UnderlyingCallStats
from schwab_dashboard.application.formatting import compact_decimal

if TYPE_CHECKING:
    from schwab_dashboard.application.dashboard.models import LiveOpenOptionPosition

D = Decimal


def evaluate_call_expiration_pressure(
    underlying: UnderlyingCallStats,
) -> DeskAlert | None:
    qualifying_calls = tuple(
        (call, level)
        for call in underlying.open_call_clocks
        if (
            level := _proximity_level(
                distance_percent=call.strike_distance_percent,
                days_to_expiration=call.days_to_expiration,
            )
        )
        is not None
    )
    if not qualifying_calls:
        return None
    call, level = max(
        qualifying_calls,
        key=lambda candidate: (
            _priority(candidate[1]),
            -abs(candidate[0].strike_distance_percent),
            -candidate[0].days_to_expiration,
        ),
    )
    is_itm = call.strike_distance_per_share <= 0
    priority = _priority(level)
    distance = abs(call.strike_distance_per_share)
    distance_percent = abs(call.strike_distance_percent)
    mark = call.mark_per_share
    return DeskAlert(
        alert_id=option_alert_id(
            symbol=underlying.symbol,
            reason="call-proximity",
            contract_key=call.record_id,
            level=level,
            strike_distance_percent=call.strike_distance_percent,
            days_to_expiration=call.days_to_expiration,
        ),
        reason_code="call_expiration_proximity",
        level=level,
        level_label=level.friendly_label,
        symbol=underlying.symbol,
        target_id=f"{underlying.symbol.lower()}-workspace",
        headline=(
            f"{underlying.symbol} is through your ${compact_decimal(call.strike)} call"
            if is_itm
            else f"Only {distance_percent:.1f}% of air below your "
            f"${compact_decimal(call.strike)} call"
        ),
        message=(
            f"{underlying.symbol} is ${distance:.2f}/share through your "
            f"${compact_decimal(call.strike)} call, with {call.days_to_expiration} days "
            "left. The short call is still open and assignable; Nibwick is flagging the "
            "position, not predicting the outcome."
            if is_itm
            else f"{underlying.symbol} has ${distance:.2f}/share of air below your "
            f"${compact_decimal(call.strike)} call, with {call.days_to_expiration} days "
            "left. Close enough to keep on the desk—not a promise that assignment is coming."
        ),
        facts=(
            AlertFact(
                "STOCK / STRIKE",
                f"${underlying.current_price:.2f} / ${compact_decimal(call.strike)}",
            ),
            AlertFact(
                "STRIKE DISTANCE",
                f"${distance:.2f} / {distance_percent:.1f}%",
                "IN THE MONEY" if is_itm else "OUT OF THE MONEY",
            ),
            AlertFact(
                "TIME LEFT",
                f"{call.days_to_expiration} DTE",
                call.expires_on.strftime("EXP %b %d").upper(),
            ),
            AlertFact(
                "MARK / CREDIT",
                f"${mark:.2f} / ${call.entry_credit_per_share:.2f}",
                "CURRENT MARK / COLLECTED",
            ),
        ),
        priority=priority,
        method_note=(
            "TRIGGER USES STRIKE DISTANCE AND CALENDAR DAYS TO EXPIRATION. IT DOES "
            "NOT ESTIMATE ASSIGNMENT ODDS OR RECOMMEND A CLOSE OR ROLL."
        ),
        roll_scenarios=build_neutral_roll_scenarios(
            call,
            current_price=underlying.current_price,
        ),
    )


def evaluate_short_put_pressure(put: LiveOpenOptionPosition) -> DeskAlert | None:
    if (
        put.option_type.upper() != "PUT"
        or put.underlying_price is None
        or put.strike_distance_per_share is None
        or put.strike_distance_percent is None
    ):
        return None
    level = _proximity_level(
        distance_percent=put.strike_distance_percent,
        days_to_expiration=put.days_to_expiration,
    )
    if level is None:
        return None
    is_itm = put.strike_distance_per_share <= 0
    distance = abs(put.strike_distance_per_share)
    distance_percent = abs(put.strike_distance_percent)
    assignment_notional = put.strike * D("100") * D(put.contracts)
    mark = put.estimated_mark_per_share
    credit = put.entry_credit_per_share
    relation = "below" if is_itm else "above"
    return DeskAlert(
        alert_id=option_alert_id(
            symbol=put.underlying_symbol,
            reason="put-proximity",
            contract_key=put.option_symbol,
            level=level,
            strike_distance_percent=put.strike_distance_percent,
            days_to_expiration=put.days_to_expiration,
        ),
        reason_code="short_put_expiration_proximity",
        level=level,
        level_label=level.friendly_label,
        symbol=put.underlying_symbol,
        target_id=f"{put.underlying_symbol.lower()}-workspace",
        headline=(
            f"{put.underlying_symbol} is through your ${compact_decimal(put.strike)} put"
            if is_itm
            else f"{distance_percent:.1f}% cushion above your "
            f"${compact_decimal(put.strike)} put"
        ),
        message=(
            f"{put.underlying_symbol} is ${distance:.2f}/share {relation} your "
            f"${compact_decimal(put.strike)} put, with {put.days_to_expiration} days "
            f"left. Assignment would mean ${assignment_notional:,.0f} of stock at the "
            "strike before premium. That is the obligation in plain sight—not an "
            "assignment forecast."
        ),
        facts=(
            AlertFact(
                "STOCK / STRIKE",
                f"${put.underlying_price:.2f} / ${compact_decimal(put.strike)}",
            ),
            AlertFact(
                "STRIKE DISTANCE",
                f"${distance:.2f} / {distance_percent:.1f}%",
                "IN THE MONEY" if is_itm else "OUT OF THE MONEY",
            ),
            AlertFact(
                "TIME LEFT",
                f"{put.days_to_expiration} DTE",
                put.expires_on.strftime("EXP %b %d").upper(),
            ),
            AlertFact(
                "MARK / CREDIT",
                f"{_money(mark)} / {_money(credit)}",
                f"${assignment_notional:,.0f} STRIKE NOTIONAL",
            ),
        ),
        priority=_priority(level),
        method_note=(
            "TRIGGER USES STRIKE DISTANCE AND CALENDAR DAYS TO EXPIRATION. STRIKE "
            "NOTIONAL IS CONTRACTS x 100 x STRIKE; IT IS NOT A CLAIM ABOUT CASH "
            "RESERVATION, MARGIN TREATMENT, OR ASSIGNMENT ODDS."
        ),
    )


def _proximity_level(
    *,
    distance_percent: Decimal,
    days_to_expiration: int,
) -> AlertLevel | None:
    if distance_percent <= 0 and days_to_expiration <= 30:
        return AlertLevel.ATTENTION if days_to_expiration <= 7 else AlertLevel.CHECK
    if distance_percent <= D("3") and days_to_expiration <= 21:
        return AlertLevel.CHECK if days_to_expiration <= 7 else AlertLevel.WATCH
    if distance_percent <= D("7") and days_to_expiration <= 7:
        return AlertLevel.WATCH
    return None


def _priority(level: AlertLevel) -> int:
    return {
        AlertLevel.ATTENTION: 95,
        AlertLevel.CHECK: 75,
        AlertLevel.WATCH: 50,
    }[level]


def _money(value: Decimal | None) -> str:
    return f"${value:.2f}" if value is not None else "UNAVAILABLE"
