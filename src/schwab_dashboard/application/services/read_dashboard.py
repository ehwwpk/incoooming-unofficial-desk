from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from schwab_dashboard.application.alerts import build_desk_alerts
from schwab_dashboard.application.dashboard.calculations import (
    map_positions,
    summarize_allocations,
    summarize_portfolio,
    summarize_risk,
)
from schwab_dashboard.application.dashboard.covered_calls import CoveredCallPortfolioSummary
from schwab_dashboard.application.dashboard.expiration_calendar import (
    build_expiration_calendar,
)
from schwab_dashboard.application.dashboard.live_performance import build_live_performance
from schwab_dashboard.application.dashboard.live_positions import build_live_position_book
from schwab_dashboard.application.dashboard.live_underlying_stats import (
    build_live_underlying_stats,
)
from schwab_dashboard.application.dashboard.models import (
    DashboardSnapshot,
    IncomeSummary,
    RiskSummary,
)
from schwab_dashboard.application.dashboard.performance import OperatorMetricsSummary
from schwab_dashboard.application.ports.analytics import LiveAnalyticsReader
from schwab_dashboard.application.ports.repositories import UnitOfWorkFactory

ZERO = Decimal("0")


class ReadDashboard:
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        analytics_reader: LiveAnalyticsReader,
        credentials_configured: bool,
        token_available: bool,
    ) -> None:
        self._uow_factory = uow_factory
        self._analytics_reader = analytics_reader
        self._credentials_configured = credentials_configured
        self._token_available = token_available

    def execute(self) -> DashboardSnapshot:
        with self._uow_factory() as uow:
            latest_sync = uow.sync_runs.latest()
            accounts = uow.accounts.list_summaries()
            positions = map_positions(uow.positions.list_latest())
            balances = uow.balances.list_latest()

        option_market = self._analytics_reader.list_latest_option_market()
        underlying_market = self._analytics_reader.list_latest_underlying_market()
        executions = self._analytics_reader.list_executions()
        cash_movements = self._analytics_reader.list_cash_movements()
        lifecycle_events = self._analytics_reader.list_lifecycle_events()
        daily_bars = self._analytics_reader.list_daily_bars()

        as_of = (
            latest_sync.completed_at
            if latest_sync is not None and latest_sync.completed_at is not None
            else datetime.now(UTC)
        )

        portfolio = summarize_portfolio(positions, balances)
        live_book = build_live_position_book(
            positions,
            as_of=as_of.date(),
            option_market=option_market,
            underlying_market=underlying_market,
        )
        covered_capital = sum(
            (abs(item.market_value or ZERO) for item in live_book.underlyings), ZERO
        )
        performance = build_live_performance(
            executions=executions,
            cash_movements=cash_movements,
            lifecycle_events=lifecycle_events,
            live_book=live_book,
            covered_capital=covered_capital,
            as_of=as_of.date(),
        )
        underlyings = build_live_underlying_stats(
            live_book=live_book,
            positions=positions,
            executions=executions,
            cash_movements=cash_movements,
            lifecycle_events=lifecycle_events,
            daily_bars=daily_bars,
            as_of=as_of.date(),
        )
        alerts = build_desk_alerts(underlyings, as_of=as_of.date())
        has_live_records = bool(positions or executions or cash_movements or lifecycle_events)
        base_risk = summarize_risk(positions)
        risk = RiskSummary(
            buying_power_used_percent=(
                (portfolio.maintenance_requirement or ZERO)
                / portfolio.total_value
                * Decimal("100")
                if portfolio.total_value
                else ZERO
            ),
            portfolio_delta=Decimal(live_book.total_shares)
            + sum(
                (
                    -(call.delta or ZERO) * Decimal("100") * Decimal(call.contracts)
                    for call in live_book.calls
                ),
                ZERO,
            ),
            daily_theta=sum(
                (item.estimated_theta_per_day for item in live_book.underlyings), ZERO
            ),
            short_contracts=live_book.open_call_contracts,
            next_expiration=min(
                (call.expires_on for call in live_book.calls), default=None
            ),
            largest_position_percent=base_risk.largest_position_percent,
            open_campaigns=0,
        )
        return DashboardSnapshot(
            mode="live",
            as_of=as_of,
            credentials_configured=self._credentials_configured,
            token_available=self._token_available,
            latest_sync=latest_sync,
            accounts=accounts,
            portfolio=portfolio,
            income=(
                performance.income
                if has_live_records
                else IncomeSummary(
                    week=ZERO,
                    month=ZERO,
                    quarter=ZERO,
                    year_to_date=ZERO,
                    win_rate=ZERO,
                    annualized_yield=ZERO,
                )
            ),
            income_periods=performance.income_periods if has_live_records else (),
            cash_events=performance.cash_events,
            cash_activity_windows=(
                performance.cash_activity_windows if has_live_records else ()
            ),
            cash_chart_series=(),
            campaigns=(),
            covered_calls=performance.covered_calls,
            underlyings=underlyings,
            alerts=alerts,
            call_history=(),
            performance_windows=performance.performance_windows if has_live_records else (),
            monthly_performance=performance.monthly_performance if has_live_records else (),
            strategy_attribution=(),
            expiration_calendar=build_expiration_calendar(underlyings, as_of.date()),
            policies=(),
            quarter_history=(),
            operator_metrics=performance.operator_metrics,
            basis_lens=(),
            positions=positions,
            allocations=summarize_allocations(positions),
            risk=risk,
            live_position_book=live_book,
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
        open_call_mark_value=ZERO,
        open_mark_profit_loss=ZERO,
        dividends=ZERO,
        total_cash_income=ZERO,
        win_rate=ZERO,
        annualized_option_yield=ZERO,
        annualized_total_cash_yield=ZERO,
        premium_capture_percent=ZERO,
    )


def _empty_operator_metrics() -> OperatorMetricsSummary:
    return OperatorMetricsSummary(
        rolling_four_week_option_cash=ZERO,
        quarter_monthly_run_rate=ZERO,
        year_to_date_monthly_run_rate=ZERO,
        rolling_year_monthly_average=ZERO,
        rolling_three_month_average=ZERO,
        median_completed_month=ZERO,
        best_completed_month=ZERO,
        worst_completed_month=ZERO,
        completed_months=0,
        compliant_call_tickets=0,
        total_call_tickets=0,
        safe_ticket_pace_monthly=ZERO,
        contract_pace_monthly=ZERO,
        premium_capture_percent=ZERO,
        buyback_drag_percent=ZERO,
        average_strike_gap_percent=ZERO,
        average_days_to_expiration=ZERO,
        uncovered_contract_capacity=0,
    )
