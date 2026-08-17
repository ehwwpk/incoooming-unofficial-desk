from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ReturnPoint:
    date: date
    value: Decimal
    external_flow: Decimal
    daily_return_percent: Decimal | None
    cumulative_return_percent: Decimal | None
    quality: str


@dataclass(frozen=True, slots=True)
class ComparisonSeries:
    key: str
    label: str
    status: str
    return_percent: Decimal | None
    method_note: str
    points: tuple[ReturnPoint, ...]


@dataclass(frozen=True, slots=True)
class MatchedComparison:
    """Every series read on the last date all of them actually cover.

    Series end on different dates by construction: the managed book is valued
    from live broker snapshots through today, while price-derived comparisons
    cannot exist past the last published close. Reading each series' own final
    value and subtracting compares unequal windows, which reports the extra
    days of market drift as though management produced them.
    """

    status: str
    as_of: date | None
    managed_return_percent: Decimal | None
    shares_return_percent: Decimal | None
    market_return_percent: Decimal | None
    levered_market_return_percent: Decimal | None
    method_note: str


@dataclass(frozen=True, slots=True)
class ManagementEdge:
    status: str
    return_difference_percent: Decimal | None
    method_note: str


@dataclass(frozen=True, slots=True)
class RiskStatistics:
    status: str
    observations: int
    measured_days: int
    max_drawdown_percent: Decimal | None
    annualized_volatility_percent: Decimal | None
    positive_day_percent: Decimal | None
    worst_day_percent: Decimal | None
    method_note: str


@dataclass(frozen=True, slots=True)
class OptionEconomics:
    status: str
    opening_credits: Decimal
    closing_debits: Decimal
    fees: Decimal
    net_executed_cash: Decimal
    closed_campaign_result: Decimal | None
    closed_campaigns: int
    exact_closed_campaigns: int
    inferred_closed_campaigns: int
    open_mark_profit_loss: Decimal | None
    current_option_liability: Decimal | None
    campaign_cash_variance: Decimal
    slippage_status: str
    method_note: str


@dataclass(frozen=True, slots=True)
class CapitalEfficiency:
    status: str
    average_net_liquidation: Decimal | None
    latest_net_liquidation: Decimal | None
    option_cash_on_average_capital_percent: Decimal | None
    maintenance_requirement: Decimal | None
    maintenance_to_net_liquidation_percent: Decimal | None
    buying_power: Decimal | None
    available_funds: Decimal | None
    method_note: str


@dataclass(frozen=True, slots=True)
class AssignmentImpact:
    status: str
    assigned_call_contracts: int
    called_away_shares: int
    assigned_put_contracts: int
    acquired_shares: int
    period_end_upside_reference: Decimal | None
    method_note: str


@dataclass(frozen=True, slots=True)
class BenchmarkPolicyItem:
    key: str
    label: str
    role: str
    status: str
    method_note: str


@dataclass(frozen=True, slots=True)
class PerformanceSpine:
    management_edge: ManagementEdge
    risk: RiskStatistics
    option_economics: OptionEconomics
    capital_efficiency: CapitalEfficiency
    assignment_impact: AssignmentImpact
    benchmark_policy: tuple[BenchmarkPolicyItem, ...]


@dataclass(frozen=True, slots=True)
class PerformanceComparison:
    methodology_version: str
    range_label: str
    coverage_start: date | None
    coverage_end: date | None
    external_flows_excluded: Decimal
    actual: ComparisonSeries
    shares_without_options: ComparisonSeries
    option_overlay: ComparisonSeries
    market_reference: ComparisonSeries
    levered_market_reference: ComparisonSeries
    spine: PerformanceSpine
    warnings: tuple[str, ...]
    matched: MatchedComparison
