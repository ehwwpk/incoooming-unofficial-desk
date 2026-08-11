from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

ZERO = Decimal("0")
TENTH = Decimal("0.1")


@dataclass(frozen=True, slots=True)
class PerformanceWindowSummary:
    key: str
    label: str
    range_label: str
    days: int
    option_cash: Decimal
    dividends: Decimal
    total_cash: Decimal
    gross_premium: Decimal
    buyback_cost: Decimal
    call_tickets: int
    contracts: int
    completed_trades: int
    win_rate: Decimal
    annualized_option_yield: Decimal
    annualized_total_yield: Decimal
    monthly_option_run_rate: Decimal
    monthly_total_run_rate: Decimal
    premium_capture_percent: Decimal
    buyback_drag_percent: Decimal


@dataclass(frozen=True, slots=True)
class QuarterPerformanceSummary:
    label: str
    option_cash: Decimal
    dividends: Decimal
    total_cash: Decimal
    bar_percent: int


@dataclass(frozen=True, slots=True)
class MonthlyPerformanceSummary:
    label: str
    year: int
    option_cash: Decimal
    dividends: Decimal
    total_cash: Decimal
    gross_premium: Decimal
    closing_debits: Decimal
    fees: Decimal
    assigned_contracts: int
    called_away_shares: int
    average_covered_capital: Decimal
    is_partial: bool


@dataclass(frozen=True, slots=True)
class CashChartPoint:
    label: str
    premium_received: Decimal
    executed_debits: Decimal
    option_cash: Decimal
    dividends: Decimal
    total_cash: Decimal
    bar_percent: int
    credit_bar_percent: int
    debit_bar_percent: int


@dataclass(frozen=True, slots=True)
class CashChartSeries:
    key: str
    label: str
    grain: str
    points: Sequence[CashChartPoint]


@dataclass(frozen=True, slots=True)
class CashActivityItem:
    event_id: str
    occurred_on: date
    symbol: str
    action_label: str
    amount: Decimal
    contracts: int
    tone: str
    anchor_id: str


@dataclass(frozen=True, slots=True)
class CashActivityWindow:
    key: str
    label: str
    range_label: str
    premium_received: Decimal
    executed_debits: Decimal
    dividends: Decimal
    net_option_cash: Decimal
    total_strategy_cash: Decimal
    events: Sequence[CashActivityItem]


@dataclass(frozen=True, slots=True)
class StrategyAttributionSummary:
    key: str
    label: str
    actual_result: Decimal | None
    stock_only_result: Decimal | None
    active_management_difference: Decimal | None
    underlying_change: Decimal | None
    dividends: Decimal
    completed_option_result: Decimal
    open_option_mark: Decimal | None
    capped_upside: Decimal | None
    average_capital: Decimal | None
    actual_return_percent: Decimal | None
    stock_only_return_percent: Decimal | None
    status: str
    method_note: str


@dataclass(frozen=True, slots=True)
class ExpirationBucket:
    expires_on: date
    days_to_expiration: int
    positions: int
    contracts: int
    committed_shares: int
    opening_credit: Decimal
    estimated_close_value: Decimal
    nearest_strike_buffer_percent: Decimal
    event_labels: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OperatorMetricsSummary:
    rolling_four_week_option_cash: Decimal
    quarter_monthly_run_rate: Decimal
    year_to_date_monthly_run_rate: Decimal
    rolling_year_monthly_average: Decimal
    rolling_three_month_average: Decimal
    median_completed_month: Decimal
    best_completed_month: Decimal
    worst_completed_month: Decimal
    completed_months: int
    compliant_call_tickets: int
    total_call_tickets: int
    safe_ticket_pace_monthly: Decimal
    contract_pace_monthly: Decimal
    premium_capture_percent: Decimal
    buyback_drag_percent: Decimal
    average_strike_gap_percent: Decimal
    average_days_to_expiration: Decimal
    uncovered_contract_capacity: int


@dataclass(frozen=True, slots=True)
class BasisLensSummary:
    symbol: str
    original_cost_basis: Decimal
    lifetime_option_income: Decimal
    lifetime_dividends: Decimal
    lifetime_management_income: Decimal
    income_adjusted_basis: Decimal
    income_adjusted_basis_per_share: Decimal | None
    basis_offset_percent: Decimal
    capital_remaining: Decimal
    recovery_surplus: Decimal
    fully_recovered: bool


@dataclass(frozen=True, slots=True)
class CapitalRecovery:
    income_adjusted_basis: Decimal
    capital_remaining: Decimal
    recovery_surplus: Decimal
    recovered_percent: Decimal
    fully_recovered: bool


def calculate_capital_recovery(
    original_cost_basis: Decimal, management_income: Decimal
) -> CapitalRecovery:
    if original_cost_basis <= ZERO:
        raise ValueError("Original cost basis must be greater than zero")
    adjusted_basis = original_cost_basis - management_income
    return CapitalRecovery(
        income_adjusted_basis=adjusted_basis,
        capital_remaining=max(ZERO, adjusted_basis),
        recovery_surplus=max(ZERO, -adjusted_basis),
        recovered_percent=(management_income / original_cost_basis * 100).quantize(TENTH),
        fully_recovered=management_income >= original_cost_basis,
    )
