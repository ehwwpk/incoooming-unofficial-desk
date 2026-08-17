from __future__ import annotations

from collections.abc import Callable
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
from schwab_dashboard.application.dashboard.option_activity import (
    build_option_outcomes,
    build_recent_option_activity,
)
from schwab_dashboard.application.dashboard.performance import OperatorMetricsSummary
from schwab_dashboard.application.dashboard.premium_pace import build_open_premium_pace
from schwab_dashboard.application.market_time import market_date
from schwab_dashboard.application.performance.projection import build_performance_comparison
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
        clock: Callable[[], datetime] | None = None,
        margin_interest_rate_percent: Decimal = Decimal("11"),
    ) -> None:
        self._uow_factory = uow_factory
        self._analytics_reader = analytics_reader
        self._credentials_configured = credentials_configured
        self._token_available = token_available
        self._clock = clock or _utc_now
        self._margin_interest_rate_percent = margin_interest_rate_percent

    def execute(self) -> DashboardSnapshot:
        with self._uow_factory() as uow:
            latest_sync_attempt = uow.sync_runs.latest_for_source(source="schwab_full")
            latest_sync = uow.sync_runs.latest_successful(source="schwab_full")
            if latest_sync_attempt is None:
                latest_sync_attempt = uow.sync_runs.latest()
            if latest_sync is None:
                latest_sync = uow.sync_runs.latest_successful(source="schwab")
            accounts = uow.accounts.list_summaries()
            positions = map_positions(uow.positions.list_latest())
            balances = uow.balances.list_latest()

        position_history = self._analytics_reader.list_position_history()
        option_symbols = tuple(
            sorted(
                {
                    position.symbol.upper()
                    for position in positions
                    if position.asset_type.upper() == "OPTION"
                }
            )
        )
        underlying_symbols = tuple(
            sorted(
                {(position.underlying_symbol or position.symbol).upper() for position in positions}
            )
        )
        historical_stock_symbols = {
            str(row.get("symbol") or "").strip().upper()
            for row in position_history
            if str(row.get("asset_type") or "").upper() != "OPTION"
        }
        daily_bar_symbols = tuple(
            sorted({*underlying_symbols, *historical_stock_symbols, "SPY"} - {""})
        )

        option_market = self._analytics_reader.list_latest_option_market(symbols=option_symbols)
        underlying_market = self._analytics_reader.list_latest_underlying_market(
            symbols=underlying_symbols
        )
        executions = self._analytics_reader.list_executions()
        cash_movements = self._analytics_reader.list_cash_movements()
        lifecycle_events = self._analytics_reader.list_lifecycle_events()
        daily_bars = self._analytics_reader.list_daily_bars(symbols=daily_bar_symbols)
        balance_history = self._analytics_reader.list_balance_history()

        evaluated_at = self._clock()
        as_of = (
            latest_sync.completed_at
            if latest_sync is not None and latest_sync.completed_at is not None
            else evaluated_at
        )
        as_of_market_date = market_date(as_of)

        portfolio = summarize_portfolio(
            positions,
            balances,
            cash_movements=cash_movements,
            as_of=as_of,
        )
        live_book = build_live_position_book(
            positions,
            as_of=as_of_market_date,
            evaluated_at=evaluated_at,
            option_market=option_market,
            underlying_market=underlying_market,
            daily_bars=daily_bars,
            executions=executions,
        )
        open_premium_pace = build_open_premium_pace(live_book, executions)
        covered_capital = sum(
            (abs(item.market_value or ZERO) for item in live_book.underlyings), ZERO
        )
        performance = build_live_performance(
            executions=executions,
            cash_movements=cash_movements,
            lifecycle_events=lifecycle_events,
            live_book=live_book,
            covered_capital=covered_capital,
            as_of=as_of_market_date,
        )
        underlyings = build_live_underlying_stats(
            live_book=live_book,
            positions=positions,
            executions=executions,
            cash_movements=cash_movements,
            lifecycle_events=lifecycle_events,
            daily_bars=daily_bars,
            option_market=option_market,
            as_of=as_of_market_date,
        )
        alerts = build_desk_alerts(
            underlyings,
            as_of=as_of_market_date,
            put_positions=live_book.puts,
        )
        recent_option_activity = build_recent_option_activity(
            executions,
            as_of=as_of_market_date,
        )
        option_outcomes = build_option_outcomes(
            executions,
            lifecycle_events,
            as_of=as_of_market_date,
            open_call_contracts=live_book.open_call_contracts,
            open_put_contracts=live_book.open_put_contracts,
        )
        has_live_records = bool(positions or executions or cash_movements or lifecycle_events)
        base_risk = summarize_risk(positions)
        active_risk_options = tuple(
            option for option in (*live_book.calls, *live_book.puts) if option.can_close_or_roll
        )
        portfolio_delta = (
            Decimal(live_book.total_shares)
            + sum(
                (
                    -option.delta * option.contract_multiplier * Decimal(option.contracts)
                    for option in active_risk_options
                    if option.delta is not None
                ),
                ZERO,
            )
            if all(option.delta is not None for option in active_risk_options)
            else None
        )
        risk = RiskSummary(
            buying_power_used_percent=(
                (portfolio.maintenance_requirement or ZERO) / portfolio.total_value * Decimal("100")
                if portfolio.total_value
                else ZERO
            ),
            portfolio_delta=portfolio_delta,
            daily_theta=sum(
                (item.estimated_option_theta_per_day for item in live_book.underlyings),
                ZERO,
            ),
            short_contracts=live_book.open_call_contracts + live_book.open_put_contracts,
            next_expiration=min(
                (
                    option.expires_on
                    for option in (*live_book.calls, *live_book.puts)
                    if option.can_close_or_roll
                ),
                default=None,
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
            cash_activity_windows=(performance.cash_activity_windows if has_live_records else ()),
            cash_chart_series=performance.cash_chart_series if has_live_records else (),
            campaigns=(),
            covered_calls=performance.covered_calls,
            underlyings=underlyings,
            alerts=alerts,
            call_history=(),
            performance_windows=performance.performance_windows if has_live_records else (),
            monthly_performance=performance.monthly_performance if has_live_records else (),
            strategy_attribution=(),
            expiration_calendar=build_expiration_calendar(
                underlyings,
                as_of_market_date,
                put_positions=live_book.puts,
            ),
            policies=(),
            quarter_history=(),
            operator_metrics=performance.operator_metrics,
            basis_lens=(),
            positions=positions,
            allocations=summarize_allocations(positions),
            risk=risk,
            live_position_book=live_book,
            latest_sync_attempt=latest_sync_attempt,
            performance_comparison=build_performance_comparison(
                balance_history=balance_history,
                cash_movements=cash_movements,
                position_history=position_history,
                daily_bars=daily_bars,
                executions=executions,
                lifecycle_events=lifecycle_events,
                margin_interest_rate_percent=self._margin_interest_rate_percent,
            ),
            recent_option_activity=recent_option_activity,
            option_outcomes=option_outcomes,
            open_premium_pace=open_premium_pace,
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


def _utc_now() -> datetime:
    return datetime.now(UTC)


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
