from datetime import date
from decimal import Decimal

from schwab_dashboard.application.dashboard.option_clock_math import (
    put_decay_stage,
    put_effective_entry_per_share,
    put_intrinsic_value,
    short_option_term,
    short_option_value_vs_credit,
)

D = Decimal


def test_short_option_term_uses_sale_to_expiry_and_refuses_to_guess() -> None:
    missing = short_option_term(
        opened_on=None,
        expires_on=date(2026, 9, 18),
        original_days_to_expiration=48,
        days_to_expiration=30,
    )
    known = short_option_term(
        opened_on=date(2026, 8, 1),
        expires_on=date(2026, 9, 18),
        original_days_to_expiration=48,
        days_to_expiration=30,
    )
    spent = short_option_term(
        opened_on=date(2026, 9, 18),
        expires_on=date(2026, 9, 18),
        original_days_to_expiration=0,
        days_to_expiration=0,
    )

    derived = short_option_term(
        opened_on=date(2026, 8, 1),
        expires_on=date(2026, 9, 18),
        original_days_to_expiration=None,
        days_to_expiration=30,
    )

    assert missing.elapsed_time_percent is None
    assert missing.time_remaining_percent is None
    assert known.elapsed_time_percent == D("37.5")
    assert known.time_remaining_percent == D("62.5")
    assert derived.elapsed_time_percent == D("37.5")
    assert derived.time_remaining_percent == D("62.5")
    assert spent.elapsed_time_percent == D("100")
    assert spent.time_remaining_percent == D("0")


def test_option_value_track_caps_at_entry_and_reports_overrun() -> None:
    contained = short_option_value_vs_credit(
        entry_credit=D("200"),
        current_liability=D("80"),
    )
    overrun = short_option_value_vs_credit(
        entry_credit=D("100"),
        current_liability=D("140"),
    )
    empty = short_option_value_vs_credit(entry_credit=D("0"), current_liability=D("40"))

    assert contained.option_value_vs_credit_percent == D("40")
    assert contained.option_value_track_percent == D("40")
    assert contained.option_value_overrun_percent == D("0")
    assert contained.credit_capture_percent == D("60")
    assert overrun.option_value_vs_credit_percent == D("140")
    assert overrun.option_value_track_percent == D("100")
    assert overrun.option_value_overrun_percent == D("40")
    assert empty.option_value_vs_credit_percent == D("0")


def test_put_intrinsic_inverts_from_the_call_and_hides_missing_spot() -> None:
    itm = put_intrinsic_value(
        strike=D("60"),
        underlying_price=D("55"),
        multiplier=D("100"),
        contracts=2,
    )
    otm = put_intrinsic_value(
        strike=D("50"),
        underlying_price=D("60"),
        multiplier=D("100"),
        contracts=1,
    )
    missing = put_intrinsic_value(
        strike=D("50"),
        underlying_price=None,
        multiplier=D("100"),
        contracts=1,
    )

    assert itm == D("1000")
    assert otm == D("0")
    assert missing is None


def test_put_effective_entry_is_strike_minus_credit_when_credit_exists() -> None:
    assert put_effective_entry_per_share(
        strike=D("50"),
        entry_credit_per_share=D("1.20"),
    ) == D("48.80")
    assert put_effective_entry_per_share(strike=D("50"), entry_credit_per_share=None) is None


def test_put_decay_stage_does_not_invent_a_cycle_without_sale_date() -> None:
    assert put_decay_stage(3, D("10"), session_label="CLOSED", can_close_or_roll=False) == "CLOSED"
    assert (
        put_decay_stage(3, None, session_label="ACTIVE", can_close_or_roll=True) == "EXPIRING SOON"
    )
    assert put_decay_stage(21, None, session_label="ACTIVE", can_close_or_roll=True) == "OPEN TERM"
    assert (
        put_decay_stage(21, D("20"), session_label="ACTIVE", can_close_or_roll=True)
        == "EARLY CYCLE"
    )
    assert (
        put_decay_stage(21, D("50"), session_label="ACTIVE", can_close_or_roll=True) == "MID CYCLE"
    )
    assert (
        put_decay_stage(21, D("80"), session_label="ACTIVE", can_close_or_roll=True) == "LATE CYCLE"
    )
