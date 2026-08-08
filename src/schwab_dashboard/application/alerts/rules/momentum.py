from __future__ import annotations

from decimal import Decimal

from schwab_dashboard.application.alerts.models import AlertFact, AlertLevel, DeskAlert
from schwab_dashboard.application.dashboard.covered_calls import UnderlyingCallStats

D = Decimal


def evaluate_fast_move(underlying: UnderlyingCallStats) -> DeskAlert | None:
    if not underlying.open_call_clocks or len(underlying.price_points) < 6:
        return None

    five_sessions_ago = underlying.price_points[-6].price
    move = (underlying.current_price / five_sessions_ago - 1) * D("100")
    closest = min(
        underlying.open_call_clocks,
        key=lambda call: abs(call.strike - underlying.current_price),
    )
    strike_gap = (closest.strike / underlying.current_price - 1) * D("100")
    if move < D("15") or strike_gap > D("15"):
        return None

    level = AlertLevel.CHECK if move >= D("25") or strike_gap <= D("3") else AlertLevel.WATCH
    priority = 90 if level is AlertLevel.CHECK else 60
    strike_position = "above" if strike_gap >= 0 else "below"
    return DeskAlert(
        alert_id=f"{underlying.symbol.lower()}-fast-move",
        reason_code="fast_move_near_call",
        level=level,
        level_label=level.friendly_label,
        symbol=underlying.symbol,
        target_id=f"{underlying.symbol.lower()}-workspace",
        headline=f"{underlying.symbol} has moved up quickly.",
        message=(
            f"It is up {move:.1f}% over the last five trading sessions. The nearest open "
            f"call strike is ${closest.strike:.2f}, about {abs(strike_gap):.1f}% "
            f"{strike_position} today's "
            "price. Keep an eye on the distance to the strike; this note does not require "
            "an action."
        ),
        facts=(
            AlertFact("5-SESSION MOVE", f"+{move:.1f}%"),
            AlertFact("CLOSEST STRIKE", f"${closest.strike:.2f}"),
            AlertFact("DAYS TO EXPIRATION", str(closest.days_to_expiration)),
        ),
        priority=priority,
    )
