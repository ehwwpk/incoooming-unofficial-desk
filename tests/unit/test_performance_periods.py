from __future__ import annotations

from datetime import UTC, date, datetime

from schwab_dashboard.application.performance.periods import PERFORMANCE_PERIODS, PerformancePeriod
from schwab_dashboard.application.services.read_performance_comparison import (
    _balances_for_period,
)


def test_performance_periods_use_calendar_months() -> None:
    through = date(2026, 8, 31)

    assert PerformancePeriod.ALL.starts_on(through=through) is None
    assert PerformancePeriod.ONE_YEAR.starts_on(through=through) == date(2025, 8, 31)
    assert PerformancePeriod.SIX_MONTHS.starts_on(through=through) == date(2026, 2, 28)
    assert PerformancePeriod.THREE_MONTHS.starts_on(through=through) == date(2026, 5, 31)
    assert PerformancePeriod.ONE_MONTH.starts_on(through=through) == date(2026, 7, 31)


def test_performance_period_selector_reads_short_to_long() -> None:
    assert [period.value for period in PERFORMANCE_PERIODS] == ["1m", "3m", "6m", "1y", "all"]


def test_balance_window_uses_latest_observation_as_its_anchor() -> None:
    balances = tuple(
        {"observed_at": datetime(2026, month, 15, 20, tzinfo=UTC)} for month in range(1, 9)
    )

    selected = _balances_for_period(balances, period=PerformancePeriod.THREE_MONTHS)

    assert [row["observed_at"].month for row in selected] == [5, 6, 7, 8]


def test_all_period_preserves_every_balance_observation() -> None:
    balances = (
        {"observed_at": datetime(2025, 1, 1, 20, tzinfo=UTC)},
        {"observed_at": datetime(2026, 8, 21, 20, tzinfo=UTC)},
    )

    assert _balances_for_period(balances, period=PerformancePeriod.ALL) == balances


def test_calculation_window_retains_one_preceding_anchor_for_gap_reconstruction() -> None:
    balances = (
        {"observed_at": datetime(2026, 7, 30, 20, tzinfo=UTC)},
        {"observed_at": datetime(2026, 8, 2, 20, tzinfo=UTC)},
        {"observed_at": datetime(2026, 9, 3, 20, tzinfo=UTC)},
    )

    selected = _balances_for_period(
        balances,
        period=PerformancePeriod.ONE_MONTH,
        include_preceding_anchor=True,
    )

    assert [row["observed_at"].date() for row in selected] == [
        date(2026, 8, 2),
        date(2026, 9, 3),
    ]
