from __future__ import annotations

from decimal import Decimal

from schwab_dashboard.application.alerts.context import build_call_review_context
from schwab_dashboard.application.alerts.models import AlertFact, AlertLevel, DeskAlert
from schwab_dashboard.application.dashboard.covered_calls import UnderlyingCallStats

D = Decimal


def evaluate_fast_move(underlying: UnderlyingCallStats) -> DeskAlert | None:
    if not underlying.open_call_clocks or len(underlying.price_points) < 6:
        return None

    five_sessions_ago = underlying.price_points[-6].price
    move = (underlying.current_price / five_sessions_ago - 1) * D("100")
    context = build_call_review_context(
        underlying,
        five_session_move_percent=move,
    )
    closest = context.call
    strike_gap = context.strike_distance_percent
    if move < D("15") or strike_gap > D("15"):
        return None

    level = AlertLevel.CHECK if move >= D("25") or strike_gap <= D("3") else AlertLevel.WATCH
    priority = 90 if level is AlertLevel.CHECK else 60
    if context.strike_distance_per_share >= 0:
        distance_message = (
            f"is ${context.strike_distance_per_share:.2f}/share "
            f"({context.strike_distance_percent:.1f}%) below your closest "
            f"${closest.strike:.2f} call—about ${context.covered_share_distance:,.0f} "
            f"across {closest.contracts * 100:,} covered shares"
        )
    else:
        distance_message = (
            f"is ${abs(context.strike_distance_per_share):.2f}/share "
            f"({abs(context.strike_distance_percent):.1f}%) above your closest "
            f"${closest.strike:.2f} call, so that call is currently in the money"
        )
    drivers = " and ".join(context.pressure.primary_drivers)

    return DeskAlert(
        alert_id=f"{underlying.symbol.lower()}-fast-move",
        reason_code="fast_move_near_call",
        level=level,
        level_label=level.friendly_label,
        symbol=underlying.symbol,
        target_id=f"{underlying.symbol.lower()}-workspace",
        headline=f"{underlying.symbol} is closing in on ${closest.strike:g}",
        message=(
            f"After a +{move:.1f}% five-session move, {underlying.symbol} "
            f"{distance_message}. Roll review pressure is "
            f"{context.pressure.label.lower()}, driven mainly by {drivers}; it is not "
            "an instruction to roll."
        ),
        facts=(
            AlertFact(
                "TO STRIKE",
                f"${abs(context.strike_distance_per_share):.2f} / "
                f"{abs(context.strike_distance_percent):.1f}%",
            ),
            AlertFact(
                "MARK / ENTRY CREDIT",
                f"${closest.mark_per_share:.2f} / ${closest.entry_credit_per_share:.2f} "
                f"· {context.mark_to_credit_ratio:.2f}x",
            ),
            AlertFact(
                "ROLL REVIEW / TIME",
                f"{context.pressure.score}/100 {context.pressure.label} "
                f"· {closest.days_to_expiration} DTE",
            ),
        ),
        priority=priority,
        method_note=(
            "ROLL REVIEW PRESSURE COMBINES STRIKE DISTANCE, FIVE-SESSION MOVE, "
            "DTE, AND CURRENT MARK VERSUS ENTRY CREDIT. IT IS A HEURISTIC—NOT "
            "A PROBABILITY OR TRADE SIGNAL."
        ),
    )
