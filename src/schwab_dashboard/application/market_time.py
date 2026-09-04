from __future__ import annotations

from datetime import UTC, date, datetime, time
from enum import StrEnum
from zoneinfo import ZoneInfo

MARKET_TIME_ZONE = ZoneInfo("America/New_York")
STANDARD_OPTION_LAST_TRADE = time(16, 0)
SCHWAB_EXERCISE_CUTOFF = time(17, 0)
WEEKDAY_LABEL_LIMIT_DAYS = 6


class OptionSessionState(StrEnum):
    """What the clock allows for a broker-reported option position."""

    ACTIVE = "active"
    EXPIRING_TODAY = "expiring_today"
    EXERCISE_WINDOW_OPEN = "exercise_window_open"
    SETTLEMENT_PENDING = "settlement_pending"
    EXPIRED_STALE = "expired_stale"

    # Compatibility alias for older callers. New code uses the explicit phase.
    CLOSED_PENDING_SETTLEMENT = "settlement_pending"

    @property
    def can_close_or_roll(self) -> bool:
        return self in {self.ACTIVE, self.EXPIRING_TODAY}

    @property
    def is_settling(self) -> bool:
        return not self.can_close_or_roll

    @property
    def label(self) -> str:
        if self is self.ACTIVE:
            return "OPEN"
        if self is self.EXPIRING_TODAY:
            return "EXPIRING TODAY"
        if self is self.EXERCISE_WINDOW_OPEN:
            return "TRADING CLOSED · EXERCISE WINDOW OPEN"
        if self is self.SETTLEMENT_PENDING:
            return "TRADING CLOSED · SETTLEMENT PENDING"
        return "EXPIRED · BROKER UPDATE PENDING"


class QuoteSession(StrEnum):
    """Whether a broker quote belongs to the session the reader is watching."""

    CURRENT_SESSION = "current_session"
    PRIOR_SESSION = "prior_session"
    UNKNOWN = "unknown"

    @property
    def is_prior_session(self) -> bool:
        return self is QuoteSession.PRIOR_SESSION


def market_date(value: date | datetime) -> date:
    """Return the U.S. equity-market date for a normalized timestamp."""

    if not isinstance(value, datetime):
        return value
    normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized.astimezone(MARKET_TIME_ZONE).date()


def ledger_market_date(value: date | datetime) -> date:
    """Return the source market date for persisted broker activity.

    SQLite removes timezone offsets. Schwab date-only activity is deliberately
    stored at midnight Eastern, which comes back as a naive midnight. Preserve
    that stated date instead of reinterpreting the sentinel as midnight UTC and
    moving an assignment, expiration, or cash event to the prior session.
    Other naive datetimes retain the project's normal UTC interpretation.
    """

    return ledger_market_datetime(value).date()


def ledger_market_datetime(value: date | datetime) -> datetime:
    """Normalize broker activity to an aware Eastern wall-clock timestamp.

    A naive midnight is the persisted form of a broker date-only record and
    therefore means midnight Eastern on that stated date. Other naive values
    are SQLite-stripped UTC instants, matching the rest of the persistence
    layer. Returning one aware timezone makes mixed-source ordering safe.
    """

    if not isinstance(value, datetime):
        return datetime.combine(value, time.min, tzinfo=MARKET_TIME_ZONE)
    if value.tzinfo is None and value.time() == time.min:
        return value.replace(tzinfo=MARKET_TIME_ZONE)
    return market_datetime(value)


def market_datetime(value: datetime) -> datetime:
    """Normalize an instant into the U.S. equity-market time zone."""

    normalized = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return normalized.astimezone(MARKET_TIME_ZONE)


def quote_session_state(
    observed_at: datetime | None,
    *,
    evaluated_at: date | datetime,
) -> QuoteSession:
    """Decide whether a quote was printed in the reader's market session."""

    if observed_at is None:
        return QuoteSession.UNKNOWN
    if market_date(observed_at) < market_date(evaluated_at):
        return QuoteSession.PRIOR_SESSION
    return QuoteSession.CURRENT_SESSION


def market_clock_label(value: datetime) -> str:
    """Render an instant as an Eastern wall-clock time."""

    market_now = market_datetime(value)
    hour = market_now.hour % 12 or 12
    meridiem = "AM" if market_now.hour < 12 else "PM"
    return f"{hour}:{market_now.minute:02d} {meridiem} ET"


def market_day_label(
    value: datetime,
    *,
    evaluated_at: date | datetime | None = None,
) -> str:
    """Name a session day, using a date once a weekday becomes ambiguous."""

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
    """Stamp a quote with an absolute Eastern session time."""

    return f"{market_day_label(value, evaluated_at=evaluated_at)} {market_clock_label(value)}"


def option_session_state(
    expires_on: date,
    evaluated_at: date | datetime,
    *,
    last_trade_at: time | None = None,
    exercise_cutoff_at: time | None = None,
) -> OptionSessionState:
    """Classify a short option without conflating DTE, trading, and settlement.

    Standard U.S. equity and ETF options stop trading at 4:00 p.m. Eastern.
    Product-specific or early-close boundaries can be supplied by the caller;
    this function deliberately does not maintain a brittle symbol allowlist.

    Trading close is not final settlement. Schwab's published customer exercise
    cutoff is 5:00 p.m. Eastern, after which broker inventory can remain visible
    overnight while exercise and assignment are processed.

    A plain date has no trustworthy clock, so same-day positions remain
    ``EXPIRING_TODAY``. Live readers pass a timezone-aware instant.
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
    wall_clock = market_now.timetz().replace(tzinfo=None)
    trade_close = last_trade_at or STANDARD_OPTION_LAST_TRADE
    exercise_cutoff = exercise_cutoff_at or SCHWAB_EXERCISE_CUTOFF
    if wall_clock < trade_close:
        return OptionSessionState.EXPIRING_TODAY
    if wall_clock < exercise_cutoff:
        return OptionSessionState.EXERCISE_WINDOW_OPEN
    return OptionSessionState.SETTLEMENT_PENDING


def option_session_cache_partition(value: datetime) -> tuple[date, str]:
    """Partition a live snapshot at boundaries that change available actions."""

    market_now = market_datetime(value)
    wall_clock = market_now.timetz().replace(tzinfo=None)
    phase = (
        "settlement_pending"
        if wall_clock >= SCHWAB_EXERCISE_CUTOFF
        else "exercise_window"
        if wall_clock >= STANDARD_OPTION_LAST_TRADE
        else "open"
    )
    return (market_now.date(), phase)
