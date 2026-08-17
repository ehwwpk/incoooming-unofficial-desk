from __future__ import annotations

from datetime import UTC, date, datetime, time
from enum import StrEnum
from zoneinfo import ZoneInfo

MARKET_TIME_ZONE = ZoneInfo("America/New_York")
OPTION_LAST_TRADE = time(16, 15)
WEEKDAY_LABEL_LIMIT_DAYS = 6


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


class QuoteSession(StrEnum):
    """Whether a broker quote belongs to the session the reader is watching.

    A sync can succeed at 9:27 a.m. on Monday and still return Friday's last
    print for a name that has not traded yet. Reporting only the sync outcome
    hides that gap, so the quote carries its own session verdict and the desk
    can label a prior-session price instead of passing it off as today's move.
    """

    CURRENT_SESSION = "current_session"
    PRIOR_SESSION = "prior_session"
    UNKNOWN = "unknown"

    @property
    def is_prior_session(self) -> bool:
        return self is QuoteSession.PRIOR_SESSION


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


def quote_session_state(
    observed_at: datetime | None,
    *,
    evaluated_at: date | datetime,
) -> QuoteSession:
    """Decide whether a quote was printed in the reader's own market session.

    The comparison runs on market calendar dates rather than elapsed hours, so a
    Friday 8:00 p.m. Eastern print does not roll into Saturday through its UTC
    date, and a Pacific reader opening the desk at 6:40 a.m. Monday is judged
    against Monday in New York rather than against a local date.

    A quote with no timestamp is ``UNKNOWN`` instead of current: imported CSV
    books and demo fixtures carry no broker clock, and inventing one for them
    would be the same false confidence this classifier exists to remove.
    """

    if observed_at is None:
        return QuoteSession.UNKNOWN
    if market_date(observed_at) < market_date(evaluated_at):
        return QuoteSession.PRIOR_SESSION
    return QuoteSession.CURRENT_SESSION


def market_clock_label(value: datetime) -> str:
    """Render an instant as a wall-clock time an Eastern-market reader recognizes."""

    market_now = market_datetime(value)
    hour = market_now.hour % 12 or 12
    meridiem = "AM" if market_now.hour < 12 else "PM"
    return f"{hour}:{market_now.minute:02d} {meridiem} ET"


def market_day_label(
    value: datetime,
    *,
    evaluated_at: date | datetime | None = None,
) -> str:
    """Name a session day, switching to a calendar date once the weekday repeats.

    ``FRI`` is unambiguous for a print from the weekend just passed. Beyond a
    week it could name either Friday, so the label becomes an explicit date.
    """

    if evaluated_at is not None:
        elapsed = (market_date(evaluated_at) - market_date(value)).days
        if elapsed > WEEKDAY_LABEL_LIMIT_DAYS:
            return market_datetime(value).strftime("%b %d").upper()
    return market_datetime(value).strftime("%a").upper()


def quote_session_stamp(
    value: datetime,
    *,
    evaluated_at: date | datetime | None = None,
) -> str:
    """Stamp a quote with an absolute session time rather than an elapsed age.

    Dashboard snapshots are cached, so a relative age such as "3h ago" would
    keep aging inside the cache while the underlying quote never changed. An
    absolute Eastern stamp stays true for as long as the page is held.
    """

    return f"{market_day_label(value, evaluated_at=evaluated_at)} {market_clock_label(value)}"


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
