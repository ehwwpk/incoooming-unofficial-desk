from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from time import sleep

from schwab_dashboard.application.services.runtime_cache import (
    CachedDashboardReader,
    GenerationCache,
)


def test_generation_cache_reuses_value_until_invalidated() -> None:
    cache = GenerationCache()
    loads = 0

    def load() -> object:
        nonlocal loads
        loads += 1
        return object()

    first = cache.get_or_load(("dashboard", "schwab"), load)
    second = cache.get_or_load(("dashboard", "schwab"), load)

    assert first is second
    assert loads == 1

    cache.invalidate()
    third = cache.get_or_load(("dashboard", "schwab"), load)

    assert third is not first
    assert loads == 2


def test_generation_cache_coalesces_concurrent_cold_loads() -> None:
    cache = GenerationCache()
    guard = Lock()
    loads = 0

    def load() -> object:
        nonlocal loads
        with guard:
            loads += 1
        sleep(0.02)
        return object()

    with ThreadPoolExecutor(max_workers=6) as pool:
        values = tuple(pool.map(lambda _: cache.get_or_load("chart:CVX", load), range(6)))

    assert loads == 1
    assert all(value is values[0] for value in values)


def test_dashboard_cache_reloads_when_market_session_partition_changes() -> None:
    cache = GenerationCache()
    phase = "open"
    loads = 0

    class Reader:
        def execute(self) -> object:
            nonlocal loads
            loads += 1
            return object()

    reader = CachedDashboardReader(  # type: ignore[arg-type]
        delegate=Reader(),
        cache=cache,
        key=("dashboard", "schwab"),
        cache_partition=lambda: phase,
    )

    first = reader.execute()
    assert reader.execute() is first
    phase = "post_close"
    assert reader.execute() is not first
    assert loads == 2
