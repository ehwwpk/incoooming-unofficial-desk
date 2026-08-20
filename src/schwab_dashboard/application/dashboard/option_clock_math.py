from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

ZERO = Decimal("0")
HUNDRED = Decimal("100")


@dataclass(frozen=True, slots=True)
class OptionTermRead:
    """Calendar term used since the surviving opening sale, or nothing to guess."""

    elapsed_time_percent: Decimal | None
    time_remaining_percent: Decimal | None


@dataclass(frozen=True, slots=True)
class OptionValueRead:
    """Current option liability as a percent of opening credit."""

    option_value_vs_credit_percent: Decimal
    option_value_track_percent: Decimal
    option_value_overrun_percent: Decimal
    credit_capture_percent: Decimal


def short_option_term(
    *,
    opened_on: date | None,
    expires_on: date,
    original_days_to_expiration: int | None,
    days_to_expiration: int,
) -> OptionTermRead:
    """Return elapsed calendar share of the original sale-to-expiry span.

    The opening sale date is enough. When the original span is missing, it is
    the calendar distance from that sale to expiration. Missing opening date is
    not treated as today. Call clocks that still default ``sold_on`` to the
    as-of date live elsewhere and are not used here.
    """

    if opened_on is None:
        return OptionTermRead(elapsed_time_percent=None, time_remaining_percent=None)
    span = (
        original_days_to_expiration
        if original_days_to_expiration is not None
        else max(0, (expires_on - opened_on).days)
    )
    elapsed_days = max(0, (expires_on - opened_on).days - days_to_expiration)
    if span <= 0:
        return OptionTermRead(elapsed_time_percent=HUNDRED, time_remaining_percent=ZERO)
    elapsed = min(HUNDRED, Decimal(elapsed_days) / Decimal(span) * HUNDRED)
    return OptionTermRead(
        elapsed_time_percent=elapsed,
        time_remaining_percent=max(ZERO, HUNDRED - elapsed),
    )


def short_option_value_vs_credit(
    *,
    entry_credit: Decimal,
    current_liability: Decimal,
) -> OptionValueRead:
    """Scale 0–100% of entry credit; excess is reported, never used to rescale."""

    if entry_credit:
        versus = current_liability / entry_credit * HUNDRED
        capture = (entry_credit - current_liability) / entry_credit * HUNDRED
    else:
        versus = ZERO
        capture = ZERO
    return OptionValueRead(
        option_value_vs_credit_percent=versus,
        option_value_track_percent=min(HUNDRED, max(ZERO, versus)),
        option_value_overrun_percent=max(ZERO, versus - HUNDRED),
        credit_capture_percent=capture,
    )


def put_intrinsic_value(
    *,
    strike: Decimal,
    underlying_price: Decimal | None,
    multiplier: Decimal,
    contracts: int,
) -> Decimal:
    """Put intrinsic using spot, or zero when the underlying mark is missing."""

    spot = underlying_price if underlying_price is not None else strike
    intrinsic_per_share = max(ZERO, strike - spot)
    return intrinsic_per_share * abs(multiplier) * Decimal(contracts)


def put_effective_entry_per_share(
    *,
    strike: Decimal,
    entry_credit_per_share: Decimal | None,
) -> Decimal | None:
    """Assignment stock price after premium, when opening credit is on the position."""

    if entry_credit_per_share is None:
        return None
    return max(ZERO, strike - abs(entry_credit_per_share))


def put_decay_stage(
    days_to_expiration: int,
    elapsed_time_percent: Decimal | None,
    *,
    session_label: str,
    can_close_or_roll: bool,
) -> str:
    if not can_close_or_roll:
        return session_label
    if days_to_expiration <= 7:
        return "EXPIRING SOON"
    if elapsed_time_percent is None:
        return "OPEN TERM"
    if elapsed_time_percent < Decimal("33"):
        return "EARLY CYCLE"
    if elapsed_time_percent < Decimal("70"):
        return "MID CYCLE"
    return "LATE CYCLE"
