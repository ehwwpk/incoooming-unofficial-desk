from __future__ import annotations

from datetime import date

from schwab_dashboard.application.alerts.context import (
    DividendReviewContext,
    build_dividend_review_context,
)
from schwab_dashboard.application.alerts.models import AlertFact, AlertLevel, DeskAlert
from schwab_dashboard.application.dashboard.covered_calls import UnderlyingCallStats
from schwab_dashboard.application.formatting import compact_decimal

DIVIDEND_REVIEW_WINDOW_DAYS = 5
DIVIDEND_WATCH_WINDOW_DAYS = 2


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
        call for call in underlying.open_call_clocks if call.expires_on >= ex_date
    )
    if not crossing_calls:
        return None

    call_contexts = tuple(
        build_dividend_review_context(underlying, crossing_calls=(call,), as_of=as_of)
        for call in crossing_calls
    )
    in_the_money_calls = tuple(item for item in call_contexts if item.is_in_the_money)
    if not in_the_money_calls:
        return None

    sensitive_calls = tuple(item for item in in_the_money_calls if item.early_assignment_sensitive)
    if sensitive_calls and days_until <= DIVIDEND_WATCH_WINDOW_DAYS:
        level = AlertLevel.ATTENTION
        priority = 100
        headline = f"{underlying.symbol} call may be assigned before the dividend"
    elif sensitive_calls:
        level = AlertLevel.CHECK
        priority = 85
        headline = f"{underlying.symbol} call needs a dividend check"
    elif days_until <= DIVIDEND_WATCH_WINDOW_DAYS:
        level = AlertLevel.WATCH
        priority = 55
        headline = f"{underlying.symbol} call is in the dividend window"
    else:
        return None

    relevant_calls = sensitive_calls or in_the_money_calls
    context = min(
        relevant_calls,
        key=lambda item: abs(item.strike_distance_per_share),
    )
    exposed_contracts = sum(item.call.contracts for item in relevant_calls)
    exposed_shares = exposed_contracts * 100
    amount_in_the_money = abs(context.strike_distance_per_share)
    percent_in_the_money = abs(context.strike_distance_percent)

    if sensitive_calls:
        time_value_shortfall = underlying.dividend_per_share - context.extrinsic_per_share
        message = (
            f"{underlying.symbol} is ${amount_in_the_money:.2f}/share "
            f"({percent_in_the_money:.1f}%) above the "
            f"${compact_decimal(context.call.strike)} call "
            f"and therefore in the money, with {_days_text(days_until).lower()} "
            "until ex-dividend. Across "
            f"{exposed_contracts} contract{'s' if exposed_contracts != 1 else ''} "
            f"({exposed_shares} shares), the ${underlying.dividend_per_share:.2f} "
            f"dividend is ${time_value_shortfall:.2f}/share greater than remaining "
            f"time value. That combination raises early-assignment sensitivity. "
            "Assignment cannot be predicted; recheck the live mark before acting."
        )
    else:
        message = (
            f"{underlying.symbol} is ${amount_in_the_money:.2f}/share "
            f"({percent_in_the_money:.1f}%) above the "
            f"${compact_decimal(context.call.strike)} call "
            f"and therefore in the money, with {_days_text(days_until).lower()} "
            "until ex-dividend. Remaining "
            f"time value (${context.extrinsic_per_share:.2f}/share) is still greater "
            f"than the ${underlying.dividend_per_share:.2f} dividend, which reduces "
            "the dividend-capture incentive. Assignment is still possible, not predictable."
        )

    return DeskAlert(
        alert_id=f"{underlying.symbol.lower()}-dividend-overlap",
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
                f"· {exposed_shares} SHARES",
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
