from __future__ import annotations

from datetime import date
from decimal import Decimal

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
    crossing_contracts = sum(call.contracts for call in crossing_calls)

    closest = min(crossing_calls, key=lambda call: abs(call.strike - underlying.current_price))
    strike_gap = (closest.strike / underlying.current_price - 1) * D("100")
    risky_calls = tuple(
        call
        for call in crossing_calls
        if underlying.current_price > call.strike
        and underlying.dividend_per_share > call.remaining_extrinsic_value / D(call.contracts * 100)
    )

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
            "dividend. That combination can raise early-assignment risk, so review the "
            "live option values before the dividend date."
        )
    elif any(underlying.current_price > call.strike for call in crossing_calls):
        message = (
            "At least one call is in the money, but its remaining time value is still "
            "greater than the dividend. Nibwick is keeping it on the radar—not sounding "
            "an alarm. Check the live values again closer to the date."
        )
    else:
        message = (
            f"Your {_call_count_text(crossing_contracts)} stay open across the dividend "
            "date. They are below their strikes today, so Nibwick is pointing this out "
            "early—not sounding an assignment alarm."
        )

    return DeskAlert(
        alert_id=f"{underlying.symbol.lower()}-dividend-overlap",
        reason_code="dividend_overlap",
        level=level,
        level_label=level.friendly_label,
        symbol=underlying.symbol,
        target_id=f"{underlying.symbol.lower()}-workspace",
        headline=f"{underlying.symbol}'s dividend is getting close",
        message=message,
        facts=(
            AlertFact("DIVIDEND DATE", ex_date.strftime("%b %d").upper()),
            AlertFact("CALLS CROSSING DATE", str(crossing_contracts)),
            AlertFact("CLOSEST STRIKE GAP", f"{strike_gap:+.1f}%"),
        ),
        priority=priority,
    )


def _call_count_text(contracts: int) -> str:
    noun = "open call contract" if contracts == 1 else "open call contracts"
    return f"{contracts} {noun}"
