from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from schwab_dashboard.application.dashboard.covered_calls import (
    CallSaleRecord,
    CoveredCallPortfolioSummary,
    UnderlyingCallStats,
)
from schwab_dashboard.application.dashboard.performance import (
    BasisLensSummary,
    ManagementObjectiveSummary,
    PerformanceWindowSummary,
    QuarterPerformanceSummary,
)
from schwab_dashboard.application.ports.repositories import SyncRunSummary


@dataclass(frozen=True, slots=True)
class PortfolioSummary:
    total_value: Decimal
    invested_value: Decimal
    cash_value: Decimal
    stock_value: Decimal
    option_value: Decimal
    day_profit_loss: Decimal
    day_profit_loss_percent: Decimal


@dataclass(frozen=True, slots=True)
class IncomeSummary:
    week: Decimal
    month: Decimal
    quarter: Decimal
    year_to_date: Decimal
    win_rate: Decimal
    annualized_yield: Decimal
    monthly_target: Decimal
    target_progress_percent: Decimal


@dataclass(frozen=True, slots=True)
class IncomePeriod:
    label: str
    option_income: Decimal
    dividends: Decimal
    total: Decimal
    bar_percent: int


@dataclass(frozen=True, slots=True)
class CampaignSummary:
    symbol: str
    strategy: str
    status: str
    opened_on: date
    expires_on: date
    days_to_expiration: int
    legs: Sequence[str]
    net_option_cash: Decimal
    unrealized_profit_loss: Decimal
    collateral: Decimal
    return_on_risk_percent: Decimal
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
    campaigns: Sequence[CampaignSummary]
    covered_calls: CoveredCallPortfolioSummary
    underlyings: Sequence[UnderlyingCallStats]
    call_history: Sequence[CallSaleRecord]
    performance_windows: Sequence[PerformanceWindowSummary]
    quarter_history: Sequence[QuarterPerformanceSummary]
    objective: ManagementObjectiveSummary
    basis_lens: Sequence[BasisLensSummary]
    positions: Sequence[PositionSummary]
    allocations: Sequence[AllocationSlice]
    risk: RiskSummary

    @property
    def is_demo(self) -> bool:
        return self.mode == "demo"
