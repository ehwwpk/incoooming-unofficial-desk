from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from schwab_dashboard.application.dashboard.calculations import (
    map_positions,
    summarize_allocations,
    summarize_portfolio,
    summarize_risk,
)
from schwab_dashboard.application.dashboard.models import DashboardSnapshot, IncomeSummary
from schwab_dashboard.application.ports.repositories import UnitOfWorkFactory

ZERO = Decimal("0")


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
            latest_sync = uow.sync_runs.latest()
            accounts = uow.accounts.list_summaries()
            positions = map_positions(uow.positions.list_latest())

        return DashboardSnapshot(
            mode="live",
            as_of=(
                latest_sync.completed_at
                if latest_sync is not None and latest_sync.completed_at is not None
                else datetime.now(UTC)
            ),
            credentials_configured=self._credentials_configured,
            token_available=self._token_available,
            latest_sync=latest_sync,
            accounts=accounts,
            portfolio=summarize_portfolio(positions),
            income=IncomeSummary(
                week=ZERO,
                month=ZERO,
                quarter=ZERO,
                year_to_date=ZERO,
                win_rate=ZERO,
                annualized_yield=ZERO,
                monthly_target=ZERO,
                target_progress_percent=ZERO,
            ),
            income_periods=(),
            campaigns=(),
            positions=positions,
            allocations=summarize_allocations(positions),
            risk=summarize_risk(positions),
        )
