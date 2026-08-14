from __future__ import annotations

from datetime import UTC, datetime, timedelta

from schwab_dashboard.application.services.market_history_refresh import (
    MarketHistoryRefreshPolicy,
)


def test_history_refresh_is_immediate_then_throttled_until_interval() -> None:
    policy = MarketHistoryRefreshPolicy(minimum_interval=timedelta(hours=1))
    now = datetime(2026, 8, 13, 17, tzinfo=UTC)

    assert policy.is_due("SPY", now=now)
    policy.mark_succeeded("SPY", at=now)

    assert not policy.is_due("SPY", now=now + timedelta(minutes=59))
    assert policy.is_due("SPY", now=now + timedelta(hours=1))
    assert policy.is_due("NEE", now=now + timedelta(minutes=1))
