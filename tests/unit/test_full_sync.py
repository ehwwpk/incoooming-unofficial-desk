from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from threading import Event, Thread

import pytest

from schwab_dashboard.application.errors import SyncInProgressError
from schwab_dashboard.application.ports.repositories import UnitOfWorkFactory
from schwab_dashboard.application.services.full_sync import FullSyncCoordinator
from schwab_dashboard.application.services.sync_accounts import SyncResult
from schwab_dashboard.application.services.sync_market import MarketSyncResult
from schwab_dashboard.application.services.sync_transactions import TransactionSyncResult
from schwab_dashboard.infrastructure.runtime.auto_sync import AutoSyncWorker

NOW = datetime(2026, 8, 11, 20, 0, tzinfo=UTC)


class _Service:
    def __init__(self, result: object, calls: list[str], label: str) -> None:
        self._result = result
        self._calls = calls
        self._label = label

    def execute(self) -> object:
        self._calls.append(self._label)
        return self._result


def _coordinator(
    calls: list[str],
    *,
    uow_factory: UnitOfWorkFactory | None = None,
) -> FullSyncCoordinator:
    accounts = SyncResult(
        run_id="accounts",
        account_count=1,
        position_count=24,
        warning_count=0,
        completed_at=NOW,
    )
    activity = TransactionSyncResult(
        run_id="activity",
        account_count=1,
        transaction_count=189,
        execution_count=155,
        cash_movement_count=20,
        lifecycle_event_count=8,
        completed_at=NOW,
    )
    market = MarketSyncResult(
        underlying_quote_count=6,
        option_quote_count=789,
        daily_bar_count=753,
        completed_at=NOW,
    )
    return FullSyncCoordinator(
        accounts_factory=lambda: _Service(accounts, calls, "accounts"),  # type: ignore[arg-type]
        activity_factory=lambda: _Service(activity, calls, "activity"),  # type: ignore[arg-type]
        market_factory=lambda: _Service(market, calls, "market"),  # type: ignore[arg-type]
        enabled=True,
        interval_seconds=900,
        uow_factory=uow_factory,
    )


def test_full_sync_runs_one_serialized_pipeline_and_records_status() -> None:
    calls: list[str] = []
    coordinator = _coordinator(calls)

    result = coordinator.execute(trigger="test")
    status = coordinator.status()

    assert calls == ["accounts", "activity", "market"]
    assert result.accounts.position_count == 24
    assert result.activity.transaction_count == 189
    assert result.market.option_quote_count == 789
    assert status.running is False
    assert status.last_trigger == "test"
    assert status.last_completed_at is not None
    assert status.last_error is None


def test_full_sync_rejects_an_overlapping_second_run() -> None:
    entered = Event()
    release = Event()
    calls: list[str] = []
    coordinator = _coordinator(calls)
    original_factory = coordinator._accounts_factory

    class _BlockingService:
        def execute(self) -> object:
            entered.set()
            release.wait(timeout=2)
            return original_factory().execute()

    coordinator._accounts_factory = _BlockingService  # type: ignore[assignment]
    thread = Thread(target=lambda: coordinator.execute(trigger="background"))
    thread.start()
    assert entered.wait(timeout=1)

    with pytest.raises(SyncInProgressError, match="already running"):
        coordinator.execute(trigger="manual")

    release.set()
    thread.join(timeout=2)
    assert not thread.is_alive()


def test_auto_sync_reports_missing_authorization_without_calling_schwab() -> None:
    async def exercise() -> None:
        calls: list[str] = []
        coordinator = _coordinator(calls)
        worker = AutoSyncWorker(
            coordinator=coordinator,
            token_available=lambda: False,
            interval_seconds=60,
            startup_delay_seconds=0,
        )
        worker.start()
        await asyncio.sleep(0.02)
        await worker.stop()

        status = coordinator.status()
        assert calls == []
        assert status.last_error is not None
        assert "authorization" in status.last_error.lower()
        assert status.next_scheduled_at is not None

    asyncio.run(exercise())


def test_full_sync_persists_end_to_end_freshness(
    database_runtime: tuple[object, object, UnitOfWorkFactory],
) -> None:
    _, _, uow_factory = database_runtime
    coordinator = _coordinator([], uow_factory=uow_factory)

    coordinator.execute(trigger="test")

    with uow_factory() as uow:
        full_run = uow.sync_runs.latest_for_source(source="schwab_full")

    assert full_run is not None
    assert full_run.status == "completed"
    assert full_run.account_count == 1
    assert full_run.position_count == 24
