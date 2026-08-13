from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from schwab_dashboard.application.errors import SyncInProgressError
from schwab_dashboard.application.services.full_sync import FullSyncCoordinator

LOGGER = logging.getLogger(__name__)


class AutoSyncWorker:
    """Run bounded read-only refreshes while the local server is alive."""

    def __init__(
        self,
        *,
        coordinator: FullSyncCoordinator,
        token_available: Callable[[], bool],
        interval_seconds: int,
        startup_delay_seconds: int,
    ) -> None:
        self._coordinator = coordinator
        self._token_available = token_available
        self._interval_seconds = interval_seconds
        self._startup_delay_seconds = startup_delay_seconds
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="incoooming-auto-sync")

    async def stop(self) -> None:
        self._stop.set()
        if self._task is not None:
            await self._task

    async def _run(self) -> None:
        if await self._wait(self._startup_delay_seconds):
            return
        while not self._stop.is_set():
            if self._token_available():
                try:
                    await asyncio.to_thread(self._coordinator.execute, trigger="auto")
                except SyncInProgressError:
                    LOGGER.info("Automatic Schwab sync skipped because another sync is running.")
                except Exception:
                    LOGGER.exception("Automatic Schwab sync failed.")
            else:
                self._coordinator.note_unavailable(
                    "Schwab authorization is not available. Reconnect the account to resume."
                )

            next_run = datetime.now(UTC) + timedelta(seconds=self._interval_seconds)
            self._coordinator.schedule_next(next_run)
            if await self._wait(self._interval_seconds):
                return

    async def _wait(self, seconds: int) -> bool:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
        except TimeoutError:
            return False
        return True
