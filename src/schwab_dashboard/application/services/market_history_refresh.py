from __future__ import annotations

from datetime import datetime, timedelta
from threading import Lock


class MarketHistoryRefreshPolicy:
    """Throttle bulky rolling-history reads without delaying live quotes.

    State is intentionally process-local. A server restart refreshes history
    immediately; repeated 15-minute account syncs reuse the stored daily bars.
    """

    def __init__(self, *, minimum_interval: timedelta) -> None:
        self._minimum_interval = minimum_interval
        self._last_succeeded: dict[str, datetime] = {}
        self._lock = Lock()

    def is_due(self, symbol: str, *, now: datetime) -> bool:
        with self._lock:
            latest = self._last_succeeded.get(symbol)
        return latest is None or now - latest >= self._minimum_interval

    def mark_succeeded(self, symbol: str, *, at: datetime) -> None:
        with self._lock:
            self._last_succeeded[symbol] = at
