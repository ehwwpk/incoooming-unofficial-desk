from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any, Protocol


class LiveAnalyticsReader(Protocol):
    def list_balance_history(self) -> Sequence[dict[str, Any]]: ...

    def list_position_history(self) -> Sequence[dict[str, Any]]: ...

    def list_executions(self) -> Sequence[dict[str, Any]]: ...

    def list_cash_movements(self) -> Sequence[dict[str, Any]]: ...

    def list_lifecycle_events(self) -> Sequence[dict[str, Any]]: ...

    def list_latest_option_market(
        self,
        *,
        symbols: Sequence[str] | None = None,
        underlyings: Sequence[str] | None = None,
        expiration_on_or_after: date | None = None,
    ) -> Sequence[dict[str, Any]]: ...

    def list_latest_underlying_market(
        self, *, symbols: Sequence[str] | None = None
    ) -> Sequence[dict[str, Any]]: ...

    def list_daily_bars(
        self, *, symbols: Sequence[str] | None = None
    ) -> Sequence[dict[str, Any]]: ...

    def list_intraday_bars(
        self, *, symbols: Sequence[str] | None = None
    ) -> Sequence[dict[str, Any]]: ...
