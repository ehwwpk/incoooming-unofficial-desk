from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from schwab_dashboard.application.dashboard.models import PositionSummary
from schwab_dashboard.application.market_time import MARKET_TIME_ZONE, market_date

ZERO = Decimal("0")


def external_flow_on(
    cash_movements: Sequence[dict[str, Any]],
    day: date,
) -> Decimal:
    """Net owner contributions and withdrawals on one market date."""
    return sum(
        (
            _decimal(movement.get("amount"))
            for movement in cash_movements
            if str(movement.get("movement_type") or "").lower() == "transfer"
            and movement_date(movement.get("occurred_at")) == day
        ),
        ZERO,
    )


def external_flow_between(
    cash_movements: Sequence[dict[str, Any]],
    *,
    after: date,
    through: date,
) -> Decimal:
    """Net owner transfers in the span that ends on one valuation date.

    A chained sub-period covers more than a single calendar day whenever a
    session is skipped or a transfer settles over a weekend. Counting only
    same-day transfers would leave that cash sitting inside the sub-period
    return, reporting the owner's funding as performance.
    """
    return sum(
        (
            _decimal(movement.get("amount"))
            for movement in cash_movements
            if str(movement.get("movement_type") or "").lower() == "transfer"
            and (day := movement_date(movement.get("occurred_at"))) is not None
            and after < day <= through
        ),
        ZERO,
    )


def external_flow_between_instants(
    cash_movements: Sequence[dict[str, Any]],
    *,
    after: datetime,
    through: datetime,
    accounts: frozenset[str] | None = None,
) -> Decimal:
    """Net owner transfers after one exact anchor and through the next."""

    return sum(
        (
            _decimal(movement.get("amount"))
            for movement in cash_movements
            if str(movement.get("movement_type") or "").lower() == "transfer"
            and _belongs_to_accounts(movement, accounts)
            and (occurred_at := movement_timestamp(movement.get("occurred_at"))) is not None
            and after < occurred_at <= through
        ),
        ZERO,
    )


def has_external_flow_between_instants(
    cash_movements: Sequence[dict[str, Any]],
    *,
    after: datetime,
    through: datetime,
    accounts: frozenset[str] | None = None,
) -> bool:
    """Whether a non-zero owner flow occurs inside an exact valuation link."""

    return any(
        str(movement.get("movement_type") or "").lower() == "transfer"
        and _decimal(movement.get("amount")) != ZERO
        and _belongs_to_accounts(movement, accounts)
        and (occurred_at := movement_timestamp(movement.get("occurred_at"))) is not None
        and after < occurred_at <= through
        for movement in cash_movements
    )


def has_unexplained_cash_between_instants(
    cash_movements: Sequence[dict[str, Any]],
    *,
    after: datetime,
    through: datetime,
    accounts: frozenset[str] | None = None,
) -> bool:
    """Fail closed when unclassified cash could otherwise masquerade as P/L.

    Recognized investment cash types (fees, premiums, withholding, dividends,
    interest, and trade settlement) remain P/L; owner transfers are removed
    explicitly.  A non-zero ``other`` movement lacks enough semantics to decide
    which side of that boundary it belongs on.
    """

    unexplained_at: dict[datetime, Decimal] = defaultdict(lambda: ZERO)
    for movement in cash_movements:
        if str(movement.get("movement_type") or "").strip().lower() != "other":
            continue
        if not _belongs_to_accounts(movement, accounts):
            continue
        occurred_at = movement_timestamp(movement.get("occurred_at"))
        if occurred_at is None or not after < occurred_at <= through:
            continue
        unexplained_at[occurred_at] += _decimal(movement.get("amount"))
    # Equal-and-opposite journals at the same broker instant have no portfolio
    # cash effect.  Everything else stays unresolved rather than becoming P/L.
    return any(total != ZERO for total in unexplained_at.values())


def external_flow_on_through(
    cash_movements: Sequence[dict[str, Any]], *, day: date, through: datetime
) -> Decimal:
    start = datetime.combine(day, time.min, tzinfo=MARKET_TIME_ZONE) - timedelta(microseconds=1)
    return external_flow_between_instants(cash_movements, after=start, through=through)


def carried_external_flow(
    cash_movements: Sequence[dict[str, Any]],
    *,
    as_of: date | datetime | None,
    account_day_change: Decimal,
    positions: Sequence[PositionSummary],
) -> Decimal:
    """Carry a recent transfer only while Schwab's opening baseline is stale."""
    if (
        as_of is None
        or not positions
        or any(position.day_profit_loss is None for position in positions)
    ):
        return ZERO
    market_day = market_date(as_of)
    earliest_day = market_day - timedelta(days=4)
    recent_prior_flow = sum(
        (
            _decimal(movement.get("amount"))
            for movement in cash_movements
            if str(movement.get("movement_type") or "").lower() == "transfer"
            and (movement_day := movement_date(movement.get("occurred_at"))) is not None
            and earliest_day <= movement_day < market_day
        ),
        ZERO,
    )
    if recent_prior_flow == ZERO:
        return ZERO
    reported_position_change = sum(
        (position.day_profit_loss or ZERO for position in positions), ZERO
    )
    unadjusted_gap = abs(account_day_change - reported_position_change)
    adjusted_gap = abs(account_day_change - recent_prior_flow - reported_position_change)
    material_improvement = max(Decimal("1"), abs(recent_prior_flow) * Decimal("0.50"))
    if adjusted_gap < unadjusted_gap and unadjusted_gap - adjusted_gap >= material_improvement:
        return recent_prior_flow
    return ZERO


def movement_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        timestamp = movement_timestamp(value)
        return market_date(timestamp) if timestamp is not None else None
    text = str(value).strip().replace("Z", "+00:00")
    if not text:
        return None
    try:
        timestamp = movement_timestamp(datetime.fromisoformat(text))
        return market_date(timestamp) if timestamp is not None else None
    except ValueError:
        return date.fromisoformat(text)


def movement_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return value
        # SQLite strips offsets. The Schwab mapper deliberately uses midnight
        # Eastern for source records that provide only a date; restore that
        # sentinel rather than moving the activity to the prior market day.
        zone = MARKET_TIME_ZONE if value.time() == time.min else UTC
        return value.replace(tzinfo=zone)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=MARKET_TIME_ZONE)
    text = str(value).strip().replace("Z", "+00:00")
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed
    zone = MARKET_TIME_ZONE if parsed.time() == time.min else UTC
    return parsed.replace(tzinfo=zone)


def _decimal(value: Any) -> Decimal:
    return ZERO if value is None else Decimal(str(value))


def _belongs_to_accounts(movement: dict[str, Any], accounts: frozenset[str] | None) -> bool:
    if accounts is None:
        return True
    account = movement.get("account_id") or movement.get("account_mask")
    # Legacy/imported rows without account identity are portfolio-level and must
    # not disappear merely because newer balance rows carry stable account IDs.
    return account is None or str(account) in accounts
