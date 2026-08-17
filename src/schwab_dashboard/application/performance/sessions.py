from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

FIRST_WEEKEND_WEEKDAY = 5


@dataclass(frozen=True, slots=True)
class MarketCalendar:
    """Which dates were real trading sessions, inferred from stored daily bars.

    The reference symbol trades every regular session, so the presence of a
    stored bar is direct evidence a session happened and its absence inside the
    stored range is direct evidence one did not. That removes any need for a
    hand-maintained holiday table, which would silently rot each year.
    """

    sessions: frozenset[date]
    first_stored_session: date | None
    last_stored_session: date | None

    def is_session(self, day: date) -> bool:
        if day in self.sessions:
            return True
        inside_stored_range = (
            self.first_stored_session is not None
            and self.last_stored_session is not None
            and self.first_stored_session <= day <= self.last_stored_session
        )
        if inside_stored_range:
            return False
        # Outside the stored range there is no evidence either way. Today has no
        # bar until its close is published, so a weekday must stay eligible or
        # the current session would drop out of every return series.
        return day.weekday() < FIRST_WEEKEND_WEEKDAY


def build_market_calendar(
    daily_bars: Sequence[dict[str, Any]],
    *,
    symbol: str = "SPY",
) -> MarketCalendar:
    days = {
        row["trade_date"]
        for row in daily_bars
        if str(row.get("symbol") or "").upper() == symbol
        and isinstance(row.get("trade_date"), date)
    }
    return MarketCalendar(
        sessions=frozenset(days),
        first_stored_session=min(days) if days else None,
        last_stored_session=max(days) if days else None,
    )
