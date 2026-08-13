from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

MARKET_TIME_ZONE = ZoneInfo("America/New_York")


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
