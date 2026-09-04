from __future__ import annotations

from datetime import date
from decimal import Decimal

from schwab_dashboard.application.alerts.context import (
    DividendReviewContext,
    build_dividend_review_context,
)
from schwab_dashboard.application.alerts.identity import option_alert_id
from schwab_dashboard.application.alerts.models import AlertFact, AlertLevel, DeskAlert
from schwab_dashboard.application.dashboard.covered_calls import UnderlyingCallStats
from schwab_dashboard.application.formatting import compact_decimal

DIVIDEND_REVIEW_WINDOW_DAYS = 5
DIVIDEND_WATCH_WINDOW_DAYS = 2
ZERO = Decimal("0")


def evaluate_dividend_overlap(
    underlying: UnderlyingCallStats,
    *,
    as_of: date,
) -> DeskAlert | None:
    ex_date = underlying.next_ex_dividend_date
    if ex_date is None:
        return None

    days_until = (ex_date - as_of).days
    if not 0 <= days_until <= DIVIDEND_REVIEW_WINDOW_DAYS:
        return None

    crossing_calls = tuple(
        call
        for call in underlying.open_call_clocks
        if call.can_close_or_roll and call.expires_on >= ex_date
    )
    if not crossing_calls:
        return None

    call_contexts = tuple(
        context
        for call in crossing_calls
        if (
            context := build_dividend_review_context(
                underlying,
                crossing_calls=(call,),
                as_of=as_of,
            )
        )
        is not None
    )
    in_the_money_calls = tuple(item for item in call_contexts if item.is_in_the_money)
    if not in_the_money_calls:
        return None

    sensitive_calls = tuple(item for item in in_the_money_calls if item.early_assignment_sensitive)
    if sensitive_calls and days_until <= DIVIDEND_WATCH_WINDOW_DAYS:
        level = AlertLevel.ATTENTION
        priority = 100
    elif sensitive_calls:
        level = AlertLevel.CHECK
        priority = 85
    elif days_until <= DIVIDEND_WATCH_WINDOW_DAYS:
        level = AlertLevel.WATCH
        priority = 55
    else:
        return None

    relevant_calls = sensitive_calls or in_the_money_calls
    context = min(
        relevant_calls,
        key=lambda item: abs(item.strike_distance_per_share),
    )
    exposed_contracts = sum(item.call.contracts for item in relevant_calls)
    exposed_shares = sum((item.call.obligated_shares or ZERO for item in relevant_calls), ZERO)
    amount_in_the_money = abs(context.strike_distance_per_share)
    percent_in_the_money = abs(context.strike_distance_percent)
    if sensitive_calls:
        headline = (
            f"{underlying.symbol}'s ${compact_decimal(context.call.strike)} call has "
            "early-assignment pressure"
        )
    else:
        headline = (
            f"{underlying.symbol}'s dividend arrives before your "
            f"${compact_decimal(context.call.strike)} call expires"
        )

    if sensitive_calls:
        time_value_shortfall = underlying.dividend_per_share - context.extrinsic_per_share
        message = (
            f"{underlying.symbol} is ${amount_in_the_money:.2f}/share through your "
            f"${compact_decimal(context.call.strike)} call, and ex-dividend is "
            f"{_days_text(days_until).lower()}. Across "
            f"{exposed_contracts} contract{'s' if exposed_contracts != 1 else ''} "
            f"({compact_decimal(exposed_shares)} shares), the "
            f"${underlying.dividend_per_share:.2f} "
            f"dividend exceeds remaining time value by ${time_value_shortfall:.2f}/share. "
            "That is the classic early-assignment pressure setup—not a prediction. "
            "Check the live mark before acting."
        )
    else:
        message = (
            f"{underlying.symbol} is ${amount_in_the_money:.2f}/share through your "
            f"${compact_decimal(context.call.strike)} call, and ex-dividend is "
            f"{_days_text(days_until).lower()}. Remaining time value is "
            f"${context.extrinsic_per_share:.2f}/share, still above the "
            f"${underlying.dividend_per_share:.2f} dividend. That weakens the early-exercise "
            "incentive, but assignment remains possible."
        )

    return DeskAlert(
        alert_id=option_alert_id(
            symbol=underlying.symbol,
            reason="dividend-overlap",
            contract_key=context.call.record_id,
            level=level,
            strike_distance_percent=context.strike_distance_percent,
            days_to_expiration=context.call.days_to_expiration,
            event_key=ex_date.isoformat(),
        ),
        reason_code="dividend_overlap",
        level=level,
        level_label=level.friendly_label,
        symbol=underlying.symbol,
        target_id=f"{underlying.symbol.lower()}-workspace",
        headline=headline,
        message=message,
        facts=(
            AlertFact(
                "EX-DIVIDEND",
                ex_date.strftime("%b %d").upper(),
                _days_text(days_until),
            ),
            AlertFact(
                "EXPOSED CALL",
                f"{underlying.symbol} ${compact_decimal(context.call.strike)}C",
                f"{exposed_contracts} CONTRACT{'S' if exposed_contracts != 1 else ''} "
                f"· {compact_decimal(exposed_shares)} SHARES",
            ),
            AlertFact(
                "IN THE MONEY",
                f"${amount_in_the_money:.2f} / {percent_in_the_money:.1f}%",
                f"STOCK ${underlying.current_price:.2f}",
            ),
            AlertFact(
                "DIV / TIME VALUE",
                f"${underlying.dividend_per_share:.2f} / ${context.extrinsic_per_share:.2f}",
                _ratio_text(context),
            ),
        ),
        priority=priority,
        method_note=(
            "TRIGGER REQUIRES AN EX-DIVIDEND DATE WITHIN FIVE CALENDAR DAYS AND "
            "AT LEAST ONE IN-THE-MONEY CALL. THE HIGHEST-RISK TIER ALSO REQUIRES "
            "THE INDICATED DIVIDEND TO EXCEED REMAINING TIME VALUE. EARLY "
            "ASSIGNMENT CANNOT BE PREDICTED."
        ),
    )


def _ratio_text(context: DividendReviewContext) -> str:
    ratio = context.dividend_to_extrinsic_ratio
    return f"{ratio:.2f}x" if ratio is not None else "NO TIME VALUE"


def _days_text(days: int) -> str:
    if days == 0:
        return "TODAY"
    return f"{days} DAY{'S' if days != 1 else ''}"
