from __future__ import annotations

from datetime import UTC, date, datetime, time
from enum import StrEnum
from zoneinfo import ZoneInfo

MARKET_TIME_ZONE = ZoneInfo("America/New_York")
OPTION_LAST_TRADE = time(16, 15)


class OptionSessionState(StrEnum):
    """What the clock allows for a broker-reported option position.

    Broker inventory can remain visible after its last trading session while
    exercise, assignment, and overnight position settlement are still pending.
    Keeping that state separate from a genuinely tradable position prevents the
    dashboard from offering an impossible close or roll after the session ends.
    """

    ACTIVE = "active"
    EXPIRING_TODAY = "expiring_today"
    CLOSED_PENDING_SETTLEMENT = "closed_pending_settlement"
    EXPIRED_STALE = "expired_stale"

    @property
    def can_close_or_roll(self) -> bool:
        return self in {self.ACTIVE, self.EXPIRING_TODAY}

    @property
    def label(self) -> str:
        return {
            self.ACTIVE: "OPEN",
            self.EXPIRING_TODAY: "EXPIRING TODAY",
            self.CLOSED_PENDING_SETTLEMENT: "TRADING CLOSED · SETTLEMENT PENDING",
            self.EXPIRED_STALE: "EXPIRED · BROKER UPDATE PENDING",
        }[self]


def market_date(value: date | datetime) -> date:
    """Return the U.S. equity-market calendar date for a normalized timestamp.

    Broker timestamps persisted without an offset are normalized UTC values, so
    naive datetimes are interpreted as UTC rather than as the machine's local zone.
    Plain dates are already calendar values and pass through unchanged.
    """

    if not isinstance(value, datetime):
        return value
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized.astimezone(MARKET_TIME_ZONE).date()


def market_datetime(value: datetime) -> datetime:
    """Normalize an instant into the U.S. equity-market time zone."""

    normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized.astimezone(MARKET_TIME_ZONE)


def option_session_state(
    expires_on: date,
    evaluated_at: date | datetime,
) -> OptionSessionState:
    """Classify a short option without conflating DTE with tradability.

    The 4:15 p.m. Eastern bound is deliberately the final regular/curb close
    across the supported U.S. equity and ETF option universe. Some classes stop
    at 4:00 p.m.; using the later bound avoids falsely declaring an eligible
    contract closed while it may still trade. Exchange early-close sessions are
    a separate calendar concern and should be supplied by a future exchange
    calendar adapter rather than guessed here.

    A plain date has no trustworthy session clock, so same-day positions remain
    ``EXPIRING_TODAY``. Live readers pass a timezone-aware wall-clock instant.
    """

    if not isinstance(evaluated_at, datetime):
        if evaluated_at < expires_on:
            return OptionSessionState.ACTIVE
        if evaluated_at > expires_on:
            return OptionSessionState.EXPIRED_STALE
        return OptionSessionState.EXPIRING_TODAY

    market_now = market_datetime(evaluated_at)
    if market_now.date() < expires_on:
        return OptionSessionState.ACTIVE
    if market_now.date() > expires_on:
        return OptionSessionState.EXPIRED_STALE
    if market_now.timetz().replace(tzinfo=None) >= OPTION_LAST_TRADE:
        return OptionSessionState.CLOSED_PENDING_SETTLEMENT
    return OptionSessionState.EXPIRING_TODAY


def option_session_cache_partition(value: datetime) -> tuple[date, str]:
    """Partition a live snapshot at the boundary that changes option actions."""

    market_now = market_datetime(value)
    phase = (
        "post_close" if market_now.timetz().replace(tzinfo=None) >= OPTION_LAST_TRADE else "open"
    )
    return (market_now.date(), phase)
