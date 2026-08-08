from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
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
    target_cash_for_window: Decimal
    target_progress_percent: Decimal
    premium_capture_percent: Decimal


@dataclass(frozen=True, slots=True)
class QuarterPerformanceSummary:
    label: str
    option_cash: Decimal
    dividends: Decimal
    total_cash: Decimal
    bar_percent: int


@dataclass(frozen=True, slots=True)
class ManagementObjectiveSummary:
    monthly_option_target: Decimal
    rolling_four_week_option_cash: Decimal
    quarter_monthly_run_rate: Decimal
    year_to_date_monthly_run_rate: Decimal
    rolling_year_monthly_average: Decimal
    rolling_year_target_gap: Decimal
    rolling_year_target_progress_percent: Decimal
    target_months_hit: int
    observed_months: int
    compliant_call_tickets: int
    total_call_tickets: int
    safe_ticket_pace_monthly: Decimal
    contract_pace_monthly: Decimal
    premium_capture_percent: Decimal
    buyback_drag_percent: Decimal
    average_strike_gap_percent: Decimal
    average_days_to_expiration: Decimal
    uncovered_contract_capacity: int
    monthly_option_results: Sequence[Decimal]


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
