from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

FIRST_WEEKEND_WEEKDAY = 5
_ONE_OFF_NYSE_CLOSURES = frozenset(
    {
        date(2001, 9, 11),
        date(2001, 9, 12),
        date(2001, 9, 13),
        date(2001, 9, 14),
        date(2004, 6, 11),
        date(2007, 1, 2),
        date(2012, 10, 29),
        date(2012, 10, 30),
        date(2018, 12, 5),
    }
)


@dataclass(frozen=True, slots=True)
class MarketCalendar:
    """Which dates were real trading sessions.

    A stored reference bar is affirmative evidence that a session occurred.
    Missing market data is never evidence that the exchange was closed: regular
    weekdays are decided by the exchange calendar so a partial download cannot
    silently erase a real performance day.
    """

    sessions: frozenset[date]
    first_stored_session: date | None
    last_stored_session: date | None

    def is_session(self, day: date) -> bool:
        if day in self.sessions:
            return True
        # Use the regular schedule both inside and outside stored coverage.
        # Treating an absent SPY row as a closure confuses an incomplete vendor
        # response with an exchange holiday and drops the day from every series.
        return _is_regular_us_equity_session(day)

    def sessions_between(
        self,
        start: date,
        end: date,
        *,
        include_start: bool = False,
        include_end: bool = True,
    ) -> tuple[date, ...]:
        """Return evidenced market sessions in a bounded interval.

        Stored SPY bars provide affirmative evidence; otherwise the exchange
        schedule is used, matching ``is_session``.
        """

        if end < start:
            return ()
        cursor = start if include_start else start + timedelta(days=1)
        limit = end if include_end else end - timedelta(days=1)
        result: list[date] = []
        while cursor <= limit:
            if self.is_session(cursor):
                result.append(cursor)
            cursor += timedelta(days=1)
        return tuple(result)

    def session_span(self, start: date, end: date) -> int:
        """Number of market-session links from ``start`` through ``end``."""

        return len(self.sessions_between(start, end))


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


def _is_regular_us_equity_session(day: date) -> bool:
    if day.weekday() >= FIRST_WEEKEND_WEEKDAY or day in _ONE_OFF_NYSE_CLOSURES:
        return False
    return day not in _regular_us_equity_holidays(day.year)


def _regular_us_equity_holidays(year: int) -> frozenset[date]:
    holidays = {
        _observed_fixed_holiday(date(year, 1, 1)),
        _nth_weekday(year, 1, 0, 3),  # Martin Luther King Jr. Day
        _nth_weekday(year, 2, 0, 3),  # Washington's Birthday
        _easter_sunday(year) - timedelta(days=2),  # Good Friday
        _last_weekday(year, 5, 0),  # Memorial Day
        _observed_fixed_holiday(date(year, 7, 4)),
        _nth_weekday(year, 9, 0, 1),  # Labor Day
        _nth_weekday(year, 11, 3, 4),  # Thanksgiving
        _observed_fixed_holiday(date(year, 12, 25)),
    }
    # NYSE began observing Juneteenth in 2022.
    if year >= 2022:
        holidays.add(_observed_fixed_holiday(date(year, 6, 19)))
    # A Saturday New Year's Day closes the preceding Friday, which belongs to
    # the prior calendar year's holiday set.
    next_new_year = date(year + 1, 1, 1)
    if next_new_year.weekday() == 5:
        holidays.add(date(year, 12, 31))
    return frozenset(holidays)


def _observed_fixed_holiday(day: date) -> date:
    if day.weekday() == 5:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def _nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> date:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (occurrence - 1))


def _last_weekday(year: int, month: int, weekday: int) -> date:
    if month == 12:
        last = date(year, 12, 31)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def _easter_sunday(year: int) -> date:
    """Gregorian Easter (Anonymous Gregorian computus)."""

    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    month_adjustment = (a + 11 * h + 22 * ell) // 451
    month = (h + ell - 7 * month_adjustment + 114) // 31
    day = (h + ell - 7 * month_adjustment + 114) % 31 + 1
    return date(year, month, day)
