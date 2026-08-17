from __future__ import annotations

from collections.abc import Callable, Hashable
from threading import RLock
from typing import TypeVar, cast

from schwab_dashboard.application.dashboard.models import DashboardSnapshot
from schwab_dashboard.application.ports.dashboard import DashboardReader

T = TypeVar("T")


class GenerationCache:
    """Small process-local cache invalidated as one atomic generation.

    Holding the lock while a value is produced intentionally coalesces concurrent
    page loads after a sync. The dashboard is read-only and a single rebuild is
    preferable to several identical SQLite scans racing each other.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._generation = 0
        self._values: dict[Hashable, tuple[int, object]] = {}

    def get_or_load(self, key: Hashable, loader: Callable[[], T]) -> T:
        with self._lock:
            cached = self._values.get(key)
            if cached is not None and cached[0] == self._generation:
                return cast(T, cached[1])
            value = loader()
            self._values[key] = (self._generation, value)
            return value

    def invalidate(self) -> None:
        with self._lock:
            self._generation += 1
            self._values.clear()


class CachedDashboardReader:
    def __init__(
        self,
        *,
        delegate: DashboardReader,
        cache: GenerationCache,
        key: Hashable,
        cache_partition: Callable[[], Hashable] | None = None,
    ) -> None:
        self._delegate = delegate
        self._cache = cache
        self._key = key
        self._cache_partition = cache_partition

    def execute(self) -> DashboardSnapshot:
        key = (
            (self._key, self._cache_partition()) if self._cache_partition is not None else self._key
        )
        return self._cache.get_or_load(key, self._delegate.execute)
