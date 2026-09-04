from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ReturnPoint:
    date: Date
    value: Decimal
    external_flow: Decimal
    daily_return_percent: Decimal | None
    cumulative_return_percent: Decimal | None
    quality: str
    interval_return_percent: Decimal | None = None
    value_quality: str = "unresolved"
    return_quality: str = "unresolved"
    valuation_phase: str = "unknown"
    previous_date: Date | None = None
    session_span: int = 0
    price_coverage_percent: Decimal | None = None
    estimated_symbols: tuple[str, ...] = ()
    reconciliation_adjustment: Decimal = Decimal("0")
    anchor_start: Date | None = None
    anchor_end: Date | None = None
    valuation_subtype: str | None = None
    raw_reconstructed_value: Decimal | None = None


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
    as_of: Date | None
    managed_return_percent: Decimal | None
    shares_return_percent: Decimal | None
    market_return_percent: Decimal | None
    levered_market_return_percent: Decimal | None
    method_note: str
    quality: str = "unresolved"


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
    reconstructed_observations: int = 0


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
    quality: str = "unresolved"
    observed_sessions: int = 0
    derived_sessions: int = 0
    estimated_sessions: int = 0
    unresolved_sessions: int = 0


@dataclass(frozen=True, slots=True)
class AssignmentImpact:
    status: str
    assigned_call_contracts: int
    called_away_shares: Decimal
    assigned_put_contracts: int
    acquired_shares: Decimal
    period_end_upside_reference: Decimal | None
    method_note: str
    unknown_side_assignments: int = 0
    unknown_side_contracts: int = 0
    reference_as_of: Date | None = None
    reference_age_days: int | None = None
    reference_quality: str = "not_applicable"


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
    coverage_start: Date | None
    coverage_end: Date | None
    external_flows_excluded: Decimal
    actual: ComparisonSeries
    shares_without_options: ComparisonSeries
    option_overlay: ComparisonSeries
    market_reference: ComparisonSeries
    levered_market_reference: ComparisonSeries
    spine: PerformanceSpine
    warnings: tuple[str, ...]
    matched: MatchedComparison
    reconstructed_sessions: int = 0
    estimated_sessions: int = 0
