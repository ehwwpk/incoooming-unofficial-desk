from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from schwab_dashboard.application.alerts.context import build_call_review_context
from schwab_dashboard.application.alerts.identity import option_alert_id
from schwab_dashboard.application.alerts.models import AlertFact, AlertLevel, DeskAlert
from schwab_dashboard.application.alerts.rolls import (
    build_neutral_roll_scenarios,
    no_clean_call_roll_reason,
)
from schwab_dashboard.application.dashboard.covered_calls import UnderlyingCallStats
from schwab_dashboard.application.formatting import compact_decimal
from schwab_dashboard.domain.instruments import OptionSide

D = Decimal


def evaluate_fast_move(underlying: UnderlyingCallStats) -> DeskAlert | None:
    actionable_calls = tuple(call for call in underlying.open_call_clocks if call.can_close_or_roll)
    if not actionable_calls or len(underlying.price_points) < 6:
        return None

    five_sessions_ago = underlying.price_points[-6].price
    move = (underlying.current_price / five_sessions_ago - 1) * D("100")
    context = build_call_review_context(
        replace(underlying, open_call_clocks=actionable_calls),
        five_session_move_percent=move,
    )
    closest = context.call
    strike_gap = context.strike_distance_percent
    if move < D("15") or strike_gap > D("15"):
        return None

    level = AlertLevel.CHECK if move >= D("25") or strike_gap <= D("3") else AlertLevel.WATCH
    priority = 90 if level is AlertLevel.CHECK else 60
    if context.strike_distance_per_share >= 0:
        position_message = (
            f"The strike is still ${context.strike_distance_per_share:.2f}/share above "
            "the stock, but that cushion is thin enough to put back on the desk"
        )
        distance_detail = "OUT OF THE MONEY"
        headline = f"{underlying.symbol} is running at your ${compact_decimal(closest.strike)} call"
    else:
        position_message = (
            f"The stock is now ${abs(context.strike_distance_per_share):.2f}/share "
            "through the strike. This one belongs back on the desk"
        )
        distance_detail = "IN THE MONEY"
        headline = f"{underlying.symbol} ran through your ${compact_decimal(closest.strike)} call"
    if context.sale_to_current_move_percent >= 0:
        sale_move_message = (
            f"{underlying.symbol} is up {context.sale_to_current_move_percent:.1f}% since "
            f"you sold the ${compact_decimal(closest.strike)} call. Rude timing"
        )
    else:
        sale_move_message = (
            f"{underlying.symbol} just ran {move:.1f}% in five sessions, though it remains "
            f"{abs(context.sale_to_current_move_percent):.1f}% below the stock price when "
            f"you sold the ${compact_decimal(closest.strike)} call"
        )
    roll_scenarios = build_neutral_roll_scenarios(
        closest,
        current_price=underlying.current_price,
    )

    return DeskAlert(
        alert_id=option_alert_id(
            symbol=underlying.symbol,
            reason="fast-move",
            contract_key=closest.record_id,
            level=level,
            strike_distance_percent=strike_gap,
            days_to_expiration=closest.days_to_expiration,
        ),
        reason_code="fast_move_near_call",
        level=level,
        level_label=level.friendly_label,
        symbol=underlying.symbol,
        target_id=f"{underlying.symbol.lower()}-workspace",
        headline=headline,
        message=f"{sale_move_message}. {position_message}.",
        facts=(
            AlertFact(
                "SPOT / MOVE",
                f"${underlying.current_price:.2f}",
                f"{context.sale_to_current_move_percent:+.1f}% SINCE SALE",
            ),
            AlertFact(
                f"TO ${compact_decimal(closest.strike)} CALL",
                f"${abs(context.strike_distance_per_share):.2f} / "
                f"{abs(context.strike_distance_percent):.1f}%",
                distance_detail,
            ),
            AlertFact(
                "MARK / TIME",
                f"${closest.mark_per_share:.2f} NOW",
                f"${closest.entry_credit_per_share:.2f} COLLECTED · "
                f"{closest.days_to_expiration} DTE",
            ),
        ),
        priority=priority,
        method_note=(
            "ROLL REVIEW PRESSURE COMBINES STRIKE DISTANCE, FIVE-SESSION MOVE, "
            "DTE, AND CURRENT MARK VERSUS ENTRY CREDIT. IT IS A HEURISTIC—NOT "
            "A PROBABILITY OR TRADE SIGNAL. ROLL CHECKS USE THE CURRENT "
            "BUY-TO-CLOSE ASK AND EACH REPLACEMENT CALL'S SELL-TO-OPEN BID. "
            "DEMO QUOTES ARE SIMULATED; FEES, TAXES, SLIPPAGE, AND LATER QUOTE "
            "MOVEMENT ARE EXCLUDED."
        ),
        roll_scenarios=roll_scenarios,
        no_clean_roll_reason=no_clean_call_roll_reason(
            closest,
            current_price=underlying.current_price,
        ),
        roll_source_option_symbol=closest.record_id,
        roll_option_side=OptionSide.CALL,
    )
