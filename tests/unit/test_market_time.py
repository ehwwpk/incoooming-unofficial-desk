from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from schwab_dashboard.application.market_time import (
    OptionSessionState,
    market_date,
    option_session_cache_partition,
    option_session_state,
)

PACIFIC = ZoneInfo("America/Los_Angeles")


def test_market_date_converts_utc_midnight_to_prior_eastern_day() -> None:
    assert market_date(datetime(2026, 8, 13, 2, 0, tzinfo=UTC)) == date(2026, 8, 12)


def test_market_date_treats_persisted_naive_datetime_as_utc() -> None:
    assert market_date(datetime(2026, 8, 13, 2, 0)) == date(2026, 8, 12)


def test_market_date_observes_winter_offset_and_preserves_dates() -> None:
    assert market_date(datetime(2026, 1, 2, 4, 30, tzinfo=UTC)) == date(2026, 1, 1)
    assert market_date(date(2026, 8, 12)) == date(2026, 8, 12)


def test_friday_expiration_stops_being_actionable_after_final_option_close() -> None:
    expires_on = date(2026, 8, 14)

    assert (
        option_session_state(
            expires_on,
            datetime(2026, 8, 14, 13, 14, tzinfo=PACIFIC),
        )
        is OptionSessionState.EXPIRING_TODAY
    )
    assert (
        option_session_state(
            expires_on,
            datetime(2026, 8, 14, 13, 15, tzinfo=PACIFIC),
        )
        is OptionSessionState.CLOSED_PENDING_SETTLEMENT
    )
    assert (
        option_session_state(
            expires_on,
            datetime(2026, 8, 14, 18, 28, tzinfo=PACIFIC),
        )
        is OptionSessionState.CLOSED_PENDING_SETTLEMENT
    )


def test_prior_expiration_is_stale_while_date_only_snapshot_stays_clock_neutral() -> None:
    expires_on = date(2026, 8, 14)

    assert option_session_state(expires_on, expires_on) is OptionSessionState.EXPIRING_TODAY
    assert (
        option_session_state(
            expires_on,
            datetime(2026, 8, 15, 9, tzinfo=PACIFIC),
        )
        is OptionSessionState.EXPIRED_STALE
    )


def test_live_cache_partition_turns_over_at_the_option_close_boundary() -> None:
    before = option_session_cache_partition(datetime(2026, 8, 14, 13, 14, tzinfo=PACIFIC))
    after = option_session_cache_partition(datetime(2026, 8, 14, 13, 15, tzinfo=PACIFIC))

    assert before == (date(2026, 8, 14), "open")
    assert after == (date(2026, 8, 14), "post_close")
