from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock

from schwab_dashboard.application.errors import SyncInProgressError
from schwab_dashboard.application.ports.repositories import UnitOfWorkFactory
from schwab_dashboard.application.services.sync_accounts import (
    SyncAccountsAndPositions,
    SyncResult,
)
from schwab_dashboard.application.services.sync_market import (
    MarketSyncResult,
    SyncSchwabMarketData,
)
from schwab_dashboard.application.services.sync_transactions import (
    SyncSchwabTransactions,
    TransactionSyncResult,
)


@dataclass(frozen=True, slots=True)
class FullSyncResult:
    trigger: str
    started_at: datetime
    completed_at: datetime
    accounts: SyncResult
    activity: TransactionSyncResult
    market: MarketSyncResult


@dataclass(frozen=True, slots=True)
class SyncRuntimeStatus:
    enabled: bool
    interval_seconds: int
    running: bool
    last_trigger: str | None
    last_started_at: datetime | None
    last_completed_at: datetime | None
    last_error: str | None
    next_scheduled_at: datetime | None


class FullSyncCoordinator:
    """Serialize full broker refreshes and expose non-financial runtime state."""

    def __init__(
        self,
        *,
        accounts_factory: Callable[[], SyncAccountsAndPositions],
        activity_factory: Callable[[], SyncSchwabTransactions],
        market_factory: Callable[[], SyncSchwabMarketData],
        enabled: bool,
        interval_seconds: int,
        uow_factory: UnitOfWorkFactory | None = None,
    ) -> None:
        self._accounts_factory = accounts_factory
        self._activity_factory = activity_factory
        self._market_factory = market_factory
        self._enabled = enabled
        self._interval_seconds = interval_seconds
        self._uow_factory = uow_factory
        self._execution_lock = Lock()
        self._state_lock = Lock()
        self._running = False
        self._last_trigger: str | None = None
        self._last_started_at: datetime | None = None
        self._last_completed_at: datetime | None = None
        self._last_error: str | None = None
        self._next_scheduled_at: datetime | None = None

    def execute(self, *, trigger: str) -> FullSyncResult:
        if not self._execution_lock.acquire(blocking=False):
            raise SyncInProgressError("A Schwab sync is already running.")
        started_at = datetime.now(UTC)
        self._set_running(trigger=trigger, started_at=started_at)
        run_id: str | None = None
        try:
            run_id = self._start_run(started_at)
            accounts = self._accounts_factory().execute()
            activity = self._activity_factory().execute()
            market = self._market_factory().execute()
            completed_at = datetime.now(UTC)
            result = FullSyncResult(
                trigger=trigger,
                started_at=started_at,
                completed_at=completed_at,
                accounts=accounts,
                activity=activity,
                market=market,
            )
            self._complete_run(
                run_id,
                completed_at=completed_at,
                account_count=accounts.account_count,
                position_count=accounts.position_count,
            )
            self._set_succeeded(completed_at)
            return result
        except Exception as exc:
            self._fail_run(run_id, exc)
            self._set_failed(exc)
            raise
        finally:
            self._execution_lock.release()

    def status(self) -> SyncRuntimeStatus:
        with self._state_lock:
            return SyncRuntimeStatus(
                enabled=self._enabled,
                interval_seconds=self._interval_seconds,
                running=self._running,
                last_trigger=self._last_trigger,
                last_started_at=self._last_started_at,
                last_completed_at=self._last_completed_at,
                last_error=self._last_error,
                next_scheduled_at=self._next_scheduled_at,
            )

    def schedule_next(self, scheduled_at: datetime | None) -> None:
        with self._state_lock:
            self._next_scheduled_at = scheduled_at

    def note_unavailable(self, message: str) -> None:
        with self._state_lock:
            self._running = False
            self._last_trigger = "auto"
            self._last_started_at = datetime.now(UTC)
            self._last_error = message

    def _set_running(self, *, trigger: str, started_at: datetime) -> None:
        with self._state_lock:
            self._running = True
            self._last_trigger = trigger
            self._last_started_at = started_at
            self._last_error = None

    def _set_succeeded(self, completed_at: datetime) -> None:
        with self._state_lock:
            self._running = False
            self._last_completed_at = completed_at
            self._last_error = None

    def _set_failed(self, exc: Exception) -> None:
        with self._state_lock:
            self._running = False
            self._last_error = str(exc)[:2000]

    def _start_run(self, started_at: datetime) -> str | None:
        if self._uow_factory is None:
            return None
        with self._uow_factory() as uow:
            run_id = uow.sync_runs.start(source="schwab_full", started_at=started_at)
            uow.commit()
        return run_id

    def _complete_run(
        self,
        run_id: str | None,
        *,
        completed_at: datetime,
        account_count: int,
        position_count: int,
    ) -> None:
        if self._uow_factory is None or run_id is None:
            return
        with self._uow_factory() as uow:
            uow.sync_runs.complete(
                run_id,
                completed_at=completed_at,
                account_count=account_count,
                position_count=position_count,
            )
            uow.commit()

    def _fail_run(self, run_id: str | None, exc: Exception) -> None:
        if self._uow_factory is None or run_id is None:
            return
        try:
            with self._uow_factory() as uow:
                uow.sync_runs.fail(
                    run_id,
                    completed_at=datetime.now(UTC),
                    error_message=str(exc)[:2000],
                )
                uow.commit()
        except Exception:
            # Preserve the broker failure; status persistence must never hide its cause.
            return
