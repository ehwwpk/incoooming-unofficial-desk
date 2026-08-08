from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from schwab_dashboard.application.dashboard.calculations import (
    map_positions,
    summarize_allocations,
    summarize_portfolio,
    summarize_risk,
)
from schwab_dashboard.application.dashboard.covered_calls import CoveredCallPortfolioSummary
from schwab_dashboard.application.dashboard.models import DashboardSnapshot, IncomeSummary
from schwab_dashboard.application.dashboard.performance import ManagementObjectiveSummary
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
            covered_calls=_empty_covered_calls(),
            underlyings=(),
            call_history=(),
            performance_windows=(),
            quarter_history=(),
            objective=_empty_objective(),
            basis_lens=(),
            positions=positions,
            allocations=summarize_allocations(positions),
            risk=summarize_risk(positions),
        )


def _empty_covered_calls() -> CoveredCallPortfolioSummary:
    return CoveredCallPortfolioSummary(
        total_shares=0,
        contract_capacity=0,
        active_contracts=0,
        coverage_percent=ZERO,
        call_tickets=0,
        contracts_sold=0,
        expired_contracts=0,
        closed_contracts=0,
        rolled_contracts=0,
        assigned_contracts=0,
        called_away_shares=0,
        gross_premium=ZERO,
        buyback_cost=ZERO,
        net_option_cash=ZERO,
        realized_option_income=ZERO,
        open_call_credit=ZERO,
        dividends=ZERO,
        total_cash_income=ZERO,
        win_rate=ZERO,
        annualized_option_yield=ZERO,
        annualized_total_cash_yield=ZERO,
        premium_capture_percent=ZERO,
    )


def _empty_objective() -> ManagementObjectiveSummary:
    return ManagementObjectiveSummary(
        monthly_option_target=ZERO,
        rolling_four_week_option_cash=ZERO,
        quarter_monthly_run_rate=ZERO,
        year_to_date_monthly_run_rate=ZERO,
        rolling_year_monthly_average=ZERO,
        rolling_year_target_gap=ZERO,
        rolling_year_target_progress_percent=ZERO,
        target_months_hit=0,
        observed_months=0,
        compliant_call_tickets=0,
        total_call_tickets=0,
        safe_ticket_pace_monthly=ZERO,
        contract_pace_monthly=ZERO,
        premium_capture_percent=ZERO,
        buyback_drag_percent=ZERO,
        average_strike_gap_percent=ZERO,
        average_days_to_expiration=ZERO,
        uncovered_contract_capacity=0,
        monthly_option_results=(),
    )
