from __future__ import annotations

from datetime import date
from decimal import Decimal

from schwab_dashboard.application.alerts.context import (
    DividendReviewContext,
    build_dividend_review_context,
)
from schwab_dashboard.application.alerts.models import AlertFact, AlertLevel, DeskAlert
from schwab_dashboard.application.dashboard.covered_calls import UnderlyingCallStats

D = Decimal


def evaluate_dividend_overlap(
    underlying: UnderlyingCallStats,
    *,
    as_of: date,
) -> DeskAlert | None:
    ex_date = underlying.next_ex_dividend_date
    if ex_date is None:
        return None

    days_until = (ex_date - as_of).days
    if not 0 <= days_until <= 14:
        return None

    crossing_calls = tuple(
        call for call in underlying.open_call_clocks if call.expires_on >= ex_date
    )
    if not crossing_calls:
        return None

    context = build_dividend_review_context(
        underlying,
        crossing_calls=crossing_calls,
        as_of=as_of,
    )
    call_contexts = tuple(
        build_dividend_review_context(underlying, crossing_calls=(call,), as_of=as_of)
        for call in crossing_calls
    )
    risky_calls = tuple(item for item in call_contexts if item.early_assignment_sensitive)

    if risky_calls and days_until <= 2:
        level = AlertLevel.ATTENTION
        priority = 100
    elif risky_calls and days_until <= 7:
        level = AlertLevel.CHECK
        priority = 85
    else:
        level = AlertLevel.WATCH
        priority = 55

    if risky_calls:
        message = (
            "One or more calls are in the money and have less time value than the "
            f"${underlying.dividend_per_share:.2f} dividend. That is the specific "
            "combination that raises early-assignment sensitivity before the ex-date. "
            "Nibwick cannot predict assignment; check the live option values again."
        )
    elif any(item.is_in_the_money for item in call_contexts):
        message = (
            "At least one call is in the money, but its remaining time value is still "
            "greater than the dividend. Nibwick is keeping it on the radar—not sounding "
            "an alarm. The live time value matters more than a simple strike-distance "
            "estimate here."
        )
    else:
        message = (
            "A dividend normally pulls the stock price down, not up. "
            f"{underlying.symbol} is ${context.strike_distance_per_share:.2f}/share "
            f"({context.strike_distance_percent:.1f}%) below the closest "
            f"${context.call.strike:.2f} call. To remain near that strike after a "
            f"dividend-sized ${underlying.dividend_per_share:.2f} adjustment, it would "
            f"need to be around ${context.pre_dividend_gray_line:.2f} before ex-date—"
            f"{_signed_money(context.distance_to_gray_line_per_share)} from today."
        )

    return DeskAlert(
        alert_id=f"{underlying.symbol.lower()}-dividend-overlap",
        reason_code="dividend_overlap",
        level=level,
        level_label=level.friendly_label,
        symbol=underlying.symbol,
        target_id=f"{underlying.symbol.lower()}-workspace",
        headline=f"{underlying.symbol}'s dividend needs context",
        message=message,
        facts=(
            AlertFact(
                "EX-DIV / CALLS",
                f"{ex_date.strftime('%b %d').upper()} · {days_until}D · "
                f"{context.crossing_contracts}",
            ),
            AlertFact(
                "PRE-DIV GRAY LINE",
                f"${context.pre_dividend_gray_line:.2f} · "
                f"{_signed_money(context.distance_to_gray_line_per_share)}",
            ),
            AlertFact(
                f"DIV / ${context.call.strike:g} TIME VALUE",
                f"${underlying.dividend_per_share:.2f} / "
                f"${context.extrinsic_per_share:.2f} · {_ratio_text(context)}",
            ),
        ),
        priority=priority,
        method_note=(
            "GRAY LINE = STRIKE + INDICATED DIVIDEND. IT IS A SIMPLE EX-DATE "
            "ADJUSTMENT, NOT A PRICE FORECAST. EARLY ASSIGNMENT CANNOT BE "
            "PREDICTED."
        ),
    )


def _ratio_text(context: DividendReviewContext) -> str:
    ratio = context.dividend_to_extrinsic_ratio
    return f"{ratio:.2f}x" if ratio is not None else "NO TIME VALUE"


def _signed_money(value: Decimal) -> str:
    sign = "+" if value >= D("0") else "-"
    return f"{sign}${abs(value):.2f}"
