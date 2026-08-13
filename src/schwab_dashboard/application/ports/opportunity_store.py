from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from schwab_dashboard.domain.opportunity import RadarMode, RadarPolicy, RadarProjection


class OpportunityStore(Protocol):
    def load_policy(self, *, symbol: str, mode: RadarMode) -> RadarPolicy | None: ...

    def save_policy(self, policy: RadarPolicy) -> RadarPolicy: ...

    def create_lookup(
        self,
        *,
        symbol: str,
        mode: RadarMode,
        source: str,
        requested_at: datetime,
    ) -> str: ...

    def complete_lookup(self, projection: RadarProjection, *, completed_at: datetime) -> None: ...

    def fail_lookup(
        self,
        lookup_id: str,
        *,
        state: str,
        error_message: str,
        completed_at: datetime,
    ) -> None: ...

    def load_lookup(self, lookup_id: str) -> dict[str, Any] | None: ...

    def list_saved_symbols(self, *, source: str) -> tuple[str, ...]: ...

    def save_symbol(self, *, symbol: str, source: str, saved_at: datetime) -> None: ...

    def remove_symbol(self, *, symbol: str, source: str) -> None: ...
