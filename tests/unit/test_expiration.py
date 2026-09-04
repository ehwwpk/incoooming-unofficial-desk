from decimal import Decimal

import pytest

from schwab_dashboard.application.expiration import (
    ExpirationExpectation,
    assess_option_expiration,
)
from schwab_dashboard.application.market_time import OptionSessionState

D = Decimal


def _assessment(
    *,
    side: str = "CALL",
    strike: str = "100",
    close: str | None = "99",
    latest: str | None = "99",
    contracts: int = 2,
    multiplier: str = "100",
):
    return assess_option_expiration(
        option_side=side,
        session_state=OptionSessionState.SETTLEMENT_PENDING,
        strike=D(strike),
        contracts=contracts,
        deliverable_shares_per_contract=D(multiplier),
        official_close=D(close) if close is not None else None,
        latest_underlying_price=D(latest) if latest is not None else None,
    )


def test_open_session_has_no_expiration_assessment() -> None:
    assert (
        assess_option_expiration(
            option_side="CALL",
            session_state=OptionSessionState.EXPIRING_TODAY,
            strike=D("100"),
            contracts=1,
            deliverable_shares_per_contract=D("100"),
            official_close=D("99"),
            latest_underlying_price=D("99"),
        )
        is None
    )


def test_out_of_money_call_is_provisionally_worthless_without_interrupt() -> None:
    assessment = _assessment()

    assert assessment is not None
    assert assessment.expectation is ExpirationExpectation.EXPECTED_WORTHLESS
    assert assessment.reference_is_official_close is True
    assert assessment.reference_label == "EXPIRATION-DAY CLOSE"
    assert assessment.distance_per_share == D("1")
    assert assessment.intrinsic_value_at_reference == D("0")
    assert assessment.needs_attention is False


def test_in_the_money_call_reports_possible_called_away_shares_and_notional() -> None:
    assessment = _assessment(close="102", latest="102", contracts=3, multiplier="150")

    assert assessment is not None
    assert assessment.expectation is ExpirationExpectation.EXPECTED_ASSIGNMENT
    assert assessment.assignment_shares == 450
    assert assessment.assignment_notional == D("45000")
    assert assessment.intrinsic_value_at_reference == D("900")
    assert assessment.needs_attention is True


def test_adjusted_multiplier_does_not_truncate_expected_delivery() -> None:
    assessment = _assessment(close="102", latest="102", contracts=1, multiplier="12.5")

    assert assessment is not None
    assert assessment.assignment_shares == D("12.5")


def test_put_assignment_direction_is_opposite_the_call_direction() -> None:
    assigned = _assessment(side="PUT", strike="100", close="97", latest="97")
    worthless = _assessment(side="PUT", strike="100", close="103", latest="103")

    assert assigned is not None and worthless is not None
    assert assigned.expectation is ExpirationExpectation.EXPECTED_ASSIGNMENT
    assert assigned.intrinsic_value_at_reference == D("600")
    assert worthless.expectation is ExpirationExpectation.EXPECTED_WORTHLESS
    assert worthless.intrinsic_value_at_reference == D("0")


def test_close_near_strike_stays_uncertain_instead_of_claiming_an_outcome() -> None:
    assessment = _assessment(close="100.20", latest="100.20")

    assert assessment is not None
    assert assessment.expectation is ExpirationExpectation.NEAR_STRIKE
    assert assessment.needs_attention is True


def test_missing_expiration_close_uses_latest_price_but_flags_the_source() -> None:
    assessment = _assessment(close=None, latest="98")

    assert assessment is not None
    assert assessment.expectation is ExpirationExpectation.EXPECTED_WORTHLESS
    assert assessment.reference_label == "LATEST UNDERLYING"
    assert assessment.reference_is_official_close is False
    assert assessment.needs_attention is True


def test_after_hours_strike_cross_is_called_out_as_provisional() -> None:
    assessment = _assessment(close="99", latest="101")

    assert assessment is not None
    assert assessment.expectation is ExpirationExpectation.EXPECTED_WORTHLESS
    assert assessment.crossed_after_close is True
    assert assessment.needs_attention is True


@pytest.mark.parametrize(
    ("side", "contracts", "multiplier"),
    (("UNKNOWN", 1, "100"), ("CALL", 0, "100"), ("PUT", 1, "0")),
)
def test_invalid_expiration_inputs_are_not_guessed(
    side: str,
    contracts: int,
    multiplier: str,
) -> None:
    with pytest.raises(ValueError):
        _assessment(side=side, contracts=contracts, multiplier=multiplier)
