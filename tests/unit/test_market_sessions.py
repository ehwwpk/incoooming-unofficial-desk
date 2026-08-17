from __future__ import annotations

from datetime import date
from decimal import Decimal

from schwab_dashboard.application.performance.sessions import build_market_calendar


def test_calendar_treats_a_gap_inside_stored_coverage_as_a_closed_market() -> None:
    calendar = build_market_calendar(_spy("2026-08-13", "2026-08-14", "2026-08-17"))

    assert calendar.is_session(date(2026, 8, 14))
    # Stored SPY coverage spans the weekend, so the absence of a bar is evidence
    # the market was shut rather than evidence the sync fell behind.
    assert not calendar.is_session(date(2026, 8, 15))
    assert not calendar.is_session(date(2026, 8, 16))


def test_calendar_keeps_weekdays_beyond_stored_coverage_eligible() -> None:
    calendar = build_market_calendar(_spy("2026-08-13", "2026-08-14"))

    # Today has no close published yet; dropping it would erase the live session
    # from every return series.
    assert calendar.is_session(date(2026, 8, 17))
    assert not calendar.is_session(date(2026, 8, 15))
    assert calendar.is_session(date(2026, 8, 12))


def test_calendar_ignores_non_reference_symbols() -> None:
    bars = [
        {"symbol": "KTOS", "trade_date": date(2026, 8, 14), "close": Decimal("60")},
        *_spy("2026-08-13"),
    ]

    calendar = build_market_calendar(bars)

    assert calendar.sessions == frozenset({date(2026, 8, 13)})


def test_empty_history_falls_back_to_weekdays() -> None:
    calendar = build_market_calendar(())

    assert calendar.is_session(date(2026, 8, 17))
    assert not calendar.is_session(date(2026, 8, 15))


def _spy(*days: str) -> list[dict[str, object]]:
    return [
        {"symbol": "SPY", "trade_date": date.fromisoformat(day), "close": Decimal("640")}
        for day in days
    ]
