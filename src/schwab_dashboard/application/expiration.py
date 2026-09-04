from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from schwab_dashboard.application.market_time import OptionSessionState

ZERO = Decimal("0")
HUNDRED = Decimal("100")


class ExpirationExpectation(StrEnum):
    """Provisional expiration read; never a broker-confirmed outcome."""

    UNKNOWN = "unknown"
    EXPECTED_WORTHLESS = "expected_worthless"
    EXPECTED_ASSIGNMENT = "expected_assignment"
    NEAR_STRIKE = "near_strike"


@dataclass(frozen=True, slots=True)
class OptionExpirationAssessment:
    option_side: str
    session_state: OptionSessionState
    expectation: ExpirationExpectation
    reference_price: Decimal | None
    reference_label: str
    reference_is_official_close: bool
    latest_underlying_price: Decimal | None
    strike: Decimal
    distance_per_share: Decimal | None
    distance_percent: Decimal | None
    contracts: int
    deliverable_shares_per_contract: Decimal
    assignment_shares: Decimal
    assignment_notional: Decimal
    intrinsic_value_at_reference: Decimal | None
    crossed_after_close: bool

    @property
    def needs_attention(self) -> bool:
        return (
            self.expectation
            in {
                ExpirationExpectation.UNKNOWN,
                ExpirationExpectation.EXPECTED_ASSIGNMENT,
                ExpirationExpectation.NEAR_STRIKE,
            }
            or self.crossed_after_close
            or not self.reference_is_official_close
        )

    @property
    def expectation_label(self) -> str:
        return {
            ExpirationExpectation.UNKNOWN: "OUTCOME UNCLEAR",
            ExpirationExpectation.EXPECTED_WORTHLESS: "EXPECTED WORTHLESS",
            ExpirationExpectation.EXPECTED_ASSIGNMENT: "ASSIGNMENT EXPECTED",
            ExpirationExpectation.NEAR_STRIKE: "NEAR STRIKE · OUTCOME UNCLEAR",
        }[self.expectation]


def assess_option_expiration(
    *,
    option_side: str,
    session_state: OptionSessionState,
    strike: Decimal,
    contracts: int,
    deliverable_shares_per_contract: Decimal,
    official_close: Decimal | None,
    latest_underlying_price: Decimal | None,
) -> OptionExpirationAssessment | None:
    """Read a closed expiration session without inventing final disposition."""

    if session_state.can_close_or_roll:
        return None
    side = option_side.strip().upper()
    if side not in {"CALL", "PUT"}:
        raise ValueError("option_side must be CALL or PUT")
    if contracts <= 0:
        raise ValueError("contracts must be positive")
    delivery = abs(deliverable_shares_per_contract)
    if delivery <= ZERO:
        raise ValueError("deliverable_shares_per_contract must be positive")
    reference = official_close if official_close is not None else latest_underlying_price
    reference_label = "EXPIRATION-DAY CLOSE" if official_close is not None else "LATEST UNDERLYING"
    assignment_shares = delivery * Decimal(contracts)
    assignment_notional = strike * assignment_shares

    if reference is None:
        expectation = ExpirationExpectation.UNKNOWN
        distance = None
        distance_percent = None
        intrinsic = None
    else:
        signed_distance = reference - strike if side == "CALL" else strike - reference
        distance = abs(signed_distance)
        distance_percent = distance / strike * HUNDRED if strike else None
        near_band = max(Decimal("0.05"), strike * Decimal("0.0025"))
        if distance <= near_band:
            expectation = ExpirationExpectation.NEAR_STRIKE
        elif signed_distance > ZERO:
            expectation = ExpirationExpectation.EXPECTED_ASSIGNMENT
        else:
            expectation = ExpirationExpectation.EXPECTED_WORTHLESS
        intrinsic = max(ZERO, signed_distance) * assignment_shares

    crossed = False
    if official_close is not None and latest_underlying_price is not None:
        official_side = official_close - strike if side == "CALL" else strike - official_close
        latest_side = (
            latest_underlying_price - strike if side == "CALL" else strike - latest_underlying_price
        )
        crossed = (official_side < ZERO <= latest_side) or (latest_side < ZERO <= official_side)

    return OptionExpirationAssessment(
        option_side=side,
        session_state=session_state,
        expectation=expectation,
        reference_price=reference,
        reference_label=reference_label,
        reference_is_official_close=official_close is not None,
        latest_underlying_price=latest_underlying_price,
        strike=strike,
        distance_per_share=distance,
        distance_percent=distance_percent,
        contracts=contracts,
        deliverable_shares_per_contract=delivery,
        assignment_shares=assignment_shares,
        assignment_notional=assignment_notional,
        intrinsic_value_at_reference=intrinsic,
        crossed_after_close=crossed,
    )
