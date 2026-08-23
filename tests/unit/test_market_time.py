from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from schwab_dashboard.application.market_time import (
    OptionSessionState,
    QuoteSession,
    market_date,
    option_session_cache_partition,
    option_session_state,
    quote_session_stamp,
    quote_session_state,
)

PACIFIC = ZoneInfo("America/Los_Angeles")
EASTERN = ZoneInfo("America/New_York")
FRIDAY_CLOSE = datetime(2026, 8, 14, 16, 0, tzinfo=EASTERN)


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
            datetime(2026, 8, 14, 12, 59, tzinfo=PACIFIC),
        )
        is OptionSessionState.EXPIRING_TODAY
    )
    assert (
        option_session_state(
            expires_on,
            datetime(2026, 8, 14, 13, 0, tzinfo=PACIFIC),
        )
        is OptionSessionState.EXERCISE_WINDOW_OPEN
    )
    assert (
        option_session_state(
            expires_on,
            datetime(2026, 8, 14, 13, 59, tzinfo=PACIFIC),
        )
        is OptionSessionState.EXERCISE_WINDOW_OPEN
    )
    assert (
        option_session_state(
            expires_on,
            datetime(2026, 8, 14, 14, 0, tzinfo=PACIFIC),
        )
        is OptionSessionState.SETTLEMENT_PENDING
    )
    assert (
        option_session_state(
            expires_on,
            datetime(2026, 8, 14, 18, 28, tzinfo=PACIFIC),
        )
        is OptionSessionState.CLOSED_PENDING_SETTLEMENT
    )


def test_option_close_and_exercise_boundaries_follow_eastern_dst_from_utc() -> None:
    """The same New York wall clock resolves to different UTC hours by season."""

    summer_expiry = date(2026, 8, 21)
    winter_expiry = date(2026, 1, 16)

    assert (
        option_session_state(summer_expiry, datetime(2026, 8, 21, 19, 59, tzinfo=UTC))
        is OptionSessionState.EXPIRING_TODAY
    )
    assert (
        option_session_state(summer_expiry, datetime(2026, 8, 21, 20, 0, tzinfo=UTC))
        is OptionSessionState.EXERCISE_WINDOW_OPEN
    )
    assert (
        option_session_state(summer_expiry, datetime(2026, 8, 21, 21, 0, tzinfo=UTC))
        is OptionSessionState.SETTLEMENT_PENDING
    )
    assert (
        option_session_state(winter_expiry, datetime(2026, 1, 16, 20, 59, tzinfo=UTC))
        is OptionSessionState.EXPIRING_TODAY
    )
    assert (
        option_session_state(winter_expiry, datetime(2026, 1, 16, 21, 0, tzinfo=UTC))
        is OptionSessionState.EXERCISE_WINDOW_OPEN
    )
    assert (
        option_session_state(winter_expiry, datetime(2026, 1, 16, 22, 0, tzinfo=UTC))
        is OptionSessionState.SETTLEMENT_PENDING
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


def test_friday_close_is_prior_session_for_a_pacific_reader_on_monday_morning() -> None:
    """The exact failure this classifier exists for: a green sync over old tape."""

    monday_pre_open = datetime(2026, 8, 17, 6, 40, tzinfo=PACIFIC)

    assert (
        quote_session_state(FRIDAY_CLOSE, evaluated_at=monday_pre_open)
        is QuoteSession.PRIOR_SESSION
    )


def test_late_friday_print_does_not_roll_into_saturday_through_its_utc_date() -> None:
    friday_evening = datetime(2026, 8, 14, 20, 0, tzinfo=EASTERN)

    assert market_date(friday_evening) == date(2026, 8, 14)
    assert (
        quote_session_state(
            friday_evening,
            evaluated_at=datetime(2026, 8, 14, 21, 0, tzinfo=EASTERN),
        )
        is QuoteSession.CURRENT_SESSION
    )


def test_sunday_night_pacific_reader_is_judged_against_the_monday_market_date() -> None:
    sunday_night = datetime(2026, 8, 16, 22, 0, tzinfo=PACIFIC)

    assert market_date(sunday_night) == date(2026, 8, 17)
    assert (
        quote_session_state(FRIDAY_CLOSE, evaluated_at=sunday_night) is QuoteSession.PRIOR_SESSION
    )


def test_quote_printed_in_the_open_session_is_current() -> None:
    assert (
        quote_session_state(
            datetime(2026, 8, 17, 9, 31, tzinfo=EASTERN),
            evaluated_at=datetime(2026, 8, 17, 9, 35, tzinfo=EASTERN),
        )
        is QuoteSession.CURRENT_SESSION
    )


def test_unclocked_quote_is_unknown_rather_than_assumed_current() -> None:
    assert (
        quote_session_state(None, evaluated_at=datetime(2026, 8, 17, 9, 35, tzinfo=EASTERN))
        is QuoteSession.UNKNOWN
    )
    assert QuoteSession.UNKNOWN.is_prior_session is False


def test_quote_stamp_reads_as_an_absolute_eastern_session_time() -> None:
    assert quote_session_stamp(FRIDAY_CLOSE) == "FRI 4:00 PM ET"
    assert quote_session_stamp(datetime(2026, 8, 14, 20, 0)) == "FRI 4:00 PM ET"


def test_quote_stamp_names_a_date_once_the_weekday_could_mean_two_sessions() -> None:
    assert quote_session_stamp(FRIDAY_CLOSE, evaluated_at=date(2026, 8, 20)) == "FRI 4:00 PM ET"
    assert quote_session_stamp(FRIDAY_CLOSE, evaluated_at=date(2026, 8, 21)) == "AUG 14 4:00 PM ET"


def test_live_cache_partition_turns_over_at_the_option_close_boundary() -> None:
    before = option_session_cache_partition(datetime(2026, 8, 14, 12, 59, tzinfo=PACIFIC))
    exercise = option_session_cache_partition(datetime(2026, 8, 14, 13, 0, tzinfo=PACIFIC))
    after = option_session_cache_partition(datetime(2026, 8, 14, 14, 0, tzinfo=PACIFIC))

    assert before == (date(2026, 8, 14), "open")
    assert exercise == (date(2026, 8, 14), "exercise_window")
    assert after == (date(2026, 8, 14), "settlement_pending")


def test_nonstandard_or_early_close_boundaries_can_be_injected() -> None:
    expires_on = date(2026, 8, 14)

    assert (
        option_session_state(
            expires_on,
            datetime(2026, 8, 14, 13, 0, tzinfo=EASTERN),
            last_trade_at=time(13, 0),
            exercise_cutoff_at=time(14, 0),
        )
        is OptionSessionState.EXERCISE_WINDOW_OPEN
    )
    assert (
        option_session_state(
            expires_on,
            datetime(2026, 8, 14, 14, 0, tzinfo=EASTERN),
            last_trade_at=time(13, 0),
            exercise_cutoff_at=time(14, 0),
        )
        is OptionSessionState.SETTLEMENT_PENDING
    )
