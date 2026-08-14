from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from schwab_dashboard.application.alerts.models import DeskAlert
from schwab_dashboard.application.dashboard.covered_calls import (
    CallSaleRecord,
    CoveredCallPortfolioSummary,
    UnderlyingCallStats,
)
from schwab_dashboard.application.dashboard.performance import (
    BasisLensSummary,
    CashActivityItem,
    CashActivityWindow,
    CashChartSeries,
    ExpirationBucket,
    MonthlyPerformanceSummary,
    OperatorMetricsSummary,
    PerformanceWindowSummary,
    QuarterPerformanceSummary,
    StrategyAttributionSummary,
)
from schwab_dashboard.application.performance.models import PerformanceComparison
from schwab_dashboard.application.policy.models import UnderlyingPolicy
from schwab_dashboard.application.ports.repositories import SyncRunSummary
from schwab_dashboard.application.rolls.models import RollQuote


@dataclass(frozen=True, slots=True)
class PortfolioSummary:
    total_value: Decimal
    invested_value: Decimal
    cash_value: Decimal
    stock_value: Decimal
    option_value: Decimal
    day_profit_loss: Decimal
    day_profit_loss_percent: Decimal
    day_external_cash_flow: Decimal = Decimal("0")
    gross_position_value: Decimal = Decimal("0")
    net_position_value: Decimal = Decimal("0")
    liquidation_value: Decimal | None = None
    equity: Decimal | None = None
    margin_balance: Decimal | None = None
    buying_power: Decimal | None = None
    available_funds: Decimal | None = None
    maintenance_requirement: Decimal | None = None


@dataclass(frozen=True, slots=True)
class IncomeSummary:
    week: Decimal
    month: Decimal
    quarter: Decimal
    year_to_date: Decimal
    win_rate: Decimal
    annualized_yield: Decimal


@dataclass(frozen=True, slots=True)
class IncomePeriod:
    label: str
    option_income: Decimal
    dividends: Decimal
    total: Decimal
    bar_percent: int


@dataclass(frozen=True, slots=True)
class CampaignSummary:
    campaign_id: str
    symbol: str
    intent_label: str
    status: str
    opened_on: date
    expires_on: date
    days_to_expiration: int
    legs: Sequence[str]
    gross_opening_credit: Decimal
    closing_debits: Decimal
    fees: Decimal
    net_cash_to_date: Decimal
    realized_cash: Decimal
    open_credit: Decimal
    estimated_close_value: Decimal
    open_mark_profit_loss: Decimal
    initial_strike: Decimal
    current_strike: Decimal
    strike_change: Decimal
    days_extended: int
    called_away_shares: int
    effective_exit_price: Decimal | None
    collateral: Decimal
    cash_on_capital_percent: Decimal
    progress_percent: int


@dataclass(frozen=True, slots=True)
class PositionSummary:
    account_mask: str
    symbol: str
    description: str
    asset_type: str
    quantity: Decimal
    average_price: Decimal | None
    mark: Decimal | None
    market_value: Decimal | None
    day_profit_loss: Decimal | None
    day_profit_loss_percent: Decimal | None
    strategy: str | None
    underlying_symbol: str | None = None
    option_type: str | None = None
    expiration_date: date | None = None
    strike: Decimal | None = None
    open_profit_loss: Decimal | None = None
    contract_multiplier: Decimal | None = None
    multiplier_source: str | None = None


@dataclass(frozen=True, slots=True)
class LiveOpenOptionPosition:
    account_mask: str
    option_symbol: str
    underlying_symbol: str
    contracts: int
    expires_on: date
    days_to_expiration: int
    strike: Decimal
    entry_credit_per_share: Decimal | None
    estimated_mark_per_share: Decimal | None
    market_value: Decimal | None
    open_profit_loss: Decimal | None
    day_profit_loss: Decimal | None
    underlying_price: Decimal | None
    strike_distance_per_share: Decimal | None
    strike_distance_percent: Decimal | None
    bid_per_share: Decimal | None = None
    ask_per_share: Decimal | None = None
    implied_volatility_percent: Decimal | None = None
    delta: Decimal | None = None
    gamma: Decimal | None = None
    theta_per_share: Decimal | None = None
    vega: Decimal | None = None
    rho: Decimal | None = None
    volume: int | None = None
    open_interest: int | None = None
    quote_observed_at: datetime | None = None
    quote_quality: str | None = None
    option_type: str = "CALL"
    contract_multiplier: Decimal = Decimal("100")
    multiplier_source: str | None = None
    roll_quote_candidates: tuple[RollQuote, ...] = ()


# Compatibility name retained while the interface moves from a call-only book to
# one instrument group per underlying. New code should use LiveOpenOptionPosition.
LiveOpenCallPosition = LiveOpenOptionPosition


@dataclass(frozen=True, slots=True)
class LiveUnderlyingPosition:
    symbol: str
    description: str
    shares: int
    average_price: Decimal | None
    current_price: Decimal | None
    market_value: Decimal | None
    day_profit_loss: Decimal | None
    contract_capacity: int
    open_call_contracts: int
    covered_contracts: int
    uncovered_contracts: int
    coverage_percent: Decimal
    open_mark_profit_loss: Decimal
    calls: Sequence[LiveOpenOptionPosition]
    average_open_iv_percent: Decimal | None = None
    estimated_theta_per_day: Decimal = Decimal("0")
    puts: Sequence[LiveOpenOptionPosition] = ()
    estimated_put_theta_per_day: Decimal = Decimal("0")
    previous_close: Decimal | None = None
    current_session_change_percent: Decimal | None = None
    quote_observed_at: datetime | None = None
    quote_quality: str | None = None

    @property
    def open_put_contracts(self) -> int:
        return sum(put.contracts for put in self.puts)

    @property
    def total_open_mark_profit_loss(self) -> Decimal:
        return self.open_mark_profit_loss + sum(
            (put.open_profit_loss or Decimal("0") for put in self.puts),
            Decimal("0"),
        )

    @property
    def estimated_option_theta_per_day(self) -> Decimal:
        return self.estimated_theta_per_day + self.estimated_put_theta_per_day


@dataclass(frozen=True, slots=True)
class LivePositionBook:
    underlyings: Sequence[LiveUnderlyingPosition]
    calls: Sequence[LiveOpenOptionPosition]
    total_shares: int
    contract_capacity: int
    open_call_positions: int
    open_call_contracts: int
    covered_contracts: int
    uncovered_contracts: int
    coverage_percent: Decimal
    open_mark_profit_loss: Decimal
    puts: Sequence[LiveOpenOptionPosition] = ()
    open_put_positions: int = 0
    open_put_contracts: int = 0

    @property
    def total_open_mark_profit_loss(self) -> Decimal:
        return self.open_mark_profit_loss + sum(
            (put.open_profit_loss or Decimal("0") for put in self.puts),
            Decimal("0"),
        )

    @property
    def estimated_put_theta_per_day(self) -> Decimal:
        return sum(
            (
                -(put.theta_per_share or Decimal("0")) * Decimal("100") * Decimal(put.contracts)
                for put in self.puts
            ),
            Decimal("0"),
        )


@dataclass(frozen=True, slots=True)
class AllocationSlice:
    label: str
    value: Decimal
    percent: Decimal
    tone: str


@dataclass(frozen=True, slots=True)
class RiskSummary:
    buying_power_used_percent: Decimal
    portfolio_delta: Decimal
    daily_theta: Decimal
    short_contracts: int
    next_expiration: date | None
    largest_position_percent: Decimal
    open_campaigns: int


@dataclass(frozen=True, slots=True)
class DashboardSnapshot:
    mode: str
    as_of: datetime
    credentials_configured: bool
    token_available: bool
    latest_sync: SyncRunSummary | None
    accounts: Sequence[dict[str, Any]]
    portfolio: PortfolioSummary
    income: IncomeSummary
    income_periods: Sequence[IncomePeriod]
    cash_events: Sequence[CashActivityItem]
    cash_activity_windows: Sequence[CashActivityWindow]
    cash_chart_series: Sequence[CashChartSeries]
    campaigns: Sequence[CampaignSummary]
    covered_calls: CoveredCallPortfolioSummary
    underlyings: Sequence[UnderlyingCallStats]
    alerts: Sequence[DeskAlert]
    call_history: Sequence[CallSaleRecord]
    performance_windows: Sequence[PerformanceWindowSummary]
    monthly_performance: Sequence[MonthlyPerformanceSummary]
    strategy_attribution: Sequence[StrategyAttributionSummary]
    expiration_calendar: Sequence[ExpirationBucket]
    policies: Sequence[UnderlyingPolicy]
    quarter_history: Sequence[QuarterPerformanceSummary]
    operator_metrics: OperatorMetricsSummary
    basis_lens: Sequence[BasisLensSummary]
    positions: Sequence[PositionSummary]
    allocations: Sequence[AllocationSlice]
    risk: RiskSummary
    live_position_book: LivePositionBook | None = None
    latest_sync_attempt: SyncRunSummary | None = None
    performance_comparison: PerformanceComparison | None = None

    @property
    def is_demo(self) -> bool:
        return self.mode == "demo"
