from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from schwab_dashboard.application.ports.repositories import (
    SyncRunSummary,
    UnitOfWorkFactory,
)


@dataclass(frozen=True, slots=True)
class DashboardSnapshot:
    credentials_configured: bool
    token_available: bool
    latest_sync: SyncRunSummary | None
    accounts: Sequence[dict[str, Any]]
    positions: Sequence[dict[str, Any]]


class ReadDashboard:
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        credentials_configured: bool,
        token_available: bool,
    ) -> None:
        self._uow_factory = uow_factory
        self._credentials_configured = credentials_configured
        self._token_available = token_available

    def execute(self) -> DashboardSnapshot:
        with self._uow_factory() as uow:
            return DashboardSnapshot(
                credentials_configured=self._credentials_configured,
                token_available=self._token_available,
                latest_sync=uow.sync_runs.latest(),
                accounts=uow.accounts.list_summaries(),
                positions=uow.positions.list_latest(),
            )
