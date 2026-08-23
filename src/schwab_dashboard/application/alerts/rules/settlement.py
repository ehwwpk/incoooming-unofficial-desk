from __future__ import annotations

from decimal import Decimal

from schwab_dashboard.application.alerts.identity import option_alert_id
from schwab_dashboard.application.alerts.models import AlertFact, AlertLevel, DeskAlert
from schwab_dashboard.application.expiration import (
    ExpirationExpectation,
    OptionExpirationAssessment,
)
from schwab_dashboard.application.formatting import compact_decimal
from schwab_dashboard.domain.instruments import OptionSide


def evaluate_settlement_attention(
    *,
    symbol: str,
    option_symbol: str,
    assessment: OptionExpirationAssessment | None,
) -> DeskAlert | None:
    """Raise only consequential or uncertain post-close outcomes.

    Routine out-of-the-money settlement stays in the settlement queue without
    becoming a mascot interruption.
    """

    if assessment is None or not assessment.needs_attention:
        return None

    side = "call" if assessment.option_side == "CALL" else "put"
    strike = compact_decimal(assessment.strike)
    reference = (
        f"${assessment.reference_price:.2f}"
        if assessment.reference_price is not None
        else "unavailable"
    )
    distance = (
        f"${assessment.distance_per_share:.2f} / {assessment.distance_percent:.1f}%"
        if assessment.distance_per_share is not None and assessment.distance_percent is not None
        else "UNAVAILABLE"
    )

    if not assessment.reference_is_official_close:
        level = AlertLevel.CHECK
        headline = f"{symbol}'s closing line is not in yet"
        message = (
            f"Trading is over for your ${strike} {side}, but Incoooming only has a "
            "later or last-known stock price—not the expiration-day close. Keep this "
            "one provisional until Schwab settles the position."
        )
        priority = 100
        reason = "expiration_close_missing"
    elif assessment.crossed_after_close:
        level = AlertLevel.ATTENTION
        headline = f"{symbol} crossed ${strike} after the close"
        message = (
            f"The expiration-day close and the latest print sit on different sides of your "
            f"${strike} {side}. Trading is over, but exercise instructions can still "
            "change the final result. Wait for Schwab to settle it."
        )
        priority = 99
        reason = "post_close_strike_cross"
    elif assessment.expectation is ExpirationExpectation.NEAR_STRIKE:
        level = AlertLevel.ATTENTION
        headline = f"{symbol} finished right on the ${strike} line"
        message = (
            f"Your ${strike} {side} finished close enough to the strike that a tiny "
            "move or exercise instruction can matter. It cannot be closed or rolled "
            "now; Schwab has the final word."
        )
        priority = 97
        reason = "expiration_near_strike"
    elif assessment.expectation is ExpirationExpectation.EXPECTED_ASSIGNMENT:
        level = AlertLevel.CHECK
        if side == "call":
            consequence = f"about {assessment.assignment_shares:,} shares may be called away"
        else:
            consequence = (
                f"about {assessment.assignment_shares:,} shares may be assigned at the strike"
            )
        headline = f"{symbol} assignment looks likely"
        message = (
            f"The {assessment.reference_label.lower()} put your ${strike} {side} in the "
            f"money, so {consequence}. Trading is closed; this is a provisional read "
            "until Schwab posts the result."
        )
        priority = 90
        reason = "assignment_expected"
    else:
        level = AlertLevel.CHECK
        headline = f"{symbol}'s expiration result is still unclear"
        message = (
            f"Incoooming does not have a reliable closing price for your ${strike} "
            f"{side}. The contract is no longer tradable; wait for Schwab's settled "
            "position before treating it as expired or assigned."
        )
        priority = 88
        reason = "expiration_outcome_unclear"

    return DeskAlert(
        alert_id=option_alert_id(
            symbol=symbol,
            reason=reason,
            contract_key=option_symbol,
            level=level,
            strike_distance_percent=assessment.distance_percent or Decimal(0),
            days_to_expiration=0,
        ),
        reason_code=reason,
        level=level,
        level_label=level.friendly_label,
        symbol=symbol,
        target_id=f"{symbol.lower()}-workspace",
        headline=headline,
        message=message,
        facts=(
            AlertFact(
                assessment.reference_label,
                reference,
                assessment.expectation_label,
            ),
            AlertFact("TO STRIKE", distance),
            AlertFact(
                "POSSIBLE SHARE RESULT",
                f"{assessment.assignment_shares:,} SHARES",
                f"${assessment.assignment_notional:,.0f} AT STRIKE",
            ),
        ),
        priority=priority,
        method_note=(
            "POST-CLOSE READ ONLY. IT USES THE EXPIRATION-DAY DAILY CLOSE WHEN "
            "AVAILABLE; EXERCISE, ASSIGNMENT, AND SETTLEMENT REMAIN BROKER/OCC EVENTS."
        ),
        roll_source_option_symbol=option_symbol,
        roll_option_side=(OptionSide.CALL if side == "call" else OptionSide.PUT),
        no_clean_roll_reason=(
            "Trading has closed for this expiration. There is no live contract left "
            "to close or roll; wait for settlement."
        ),
    )
