from datetime import UTC, date, datetime

from schwab_dashboard.application.market_time import market_date


def test_market_date_converts_utc_midnight_to_prior_eastern_day() -> None:
    assert market_date(datetime(2026, 8, 13, 2, 0, tzinfo=UTC)) == date(2026, 8, 12)


def test_market_date_treats_persisted_naive_datetime_as_utc() -> None:
    assert market_date(datetime(2026, 8, 13, 2, 0)) == date(2026, 8, 12)


def test_market_date_observes_winter_offset_and_preserves_dates() -> None:
    assert market_date(datetime(2026, 1, 2, 4, 30, tzinfo=UTC)) == date(2026, 1, 1)
    assert market_date(date(2026, 8, 12)) == date(2026, 8, 12)
