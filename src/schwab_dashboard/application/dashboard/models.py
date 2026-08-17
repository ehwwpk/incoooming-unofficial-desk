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
from schwab_dashboard.application.dashboard.option_activity import (
    OptionOutcomeSummary,
    RecentOptionActivityItem,
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
from schwab_dashboard.application.market_time import (
    OptionSessionState,
    QuoteSession,
    market_day_label,
    quote_session_stamp,
)
from schwab_dashboard.application.performance.models import PerformanceComparison
from schwab_dashboard.application.policy.models import UnderlyingPolicy
from schwab_dashboard.application.ports.repositories import SyncRunSummary
from schwab_dashboard.application.risk.price_time import (
    PriceTimeRead,
    aggregate_price_time_reads,
    build_price_time_read,
)
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
    session_state: OptionSessionState = OptionSessionState.ACTIVE
    underlying_previous_close: Decimal | None = None
    underlying_week_reference_price: Decimal | None = None
    opened_on: date | None = None
    original_days_to_expiration: int | None = None

    @property
    def can_close_or_roll(self) -> bool:
        return self.session_state.can_close_or_roll

    @property
    def session_label(self) -> str:
        return self.session_state.label

    @property
    def position_scale(self) -> Decimal:
        """Return the Greek scale for this aggregated short position."""

        return abs(self.contract_multiplier) * Decimal(self.contracts)

    @property
    def position_delta_share_equivalent(self) -> Decimal | None:
        """Current option-only price exposure expressed as equivalent shares."""

        return -(self.delta * self.position_scale) if self.delta is not None else None

    @property
    def position_gamma_delta_change_per_dollar(self) -> Decimal | None:
        return -(self.gamma * self.position_scale) if self.gamma is not None else None

    @property
    def position_vega_per_volatility_point(self) -> Decimal | None:
        return -(self.vega * self.position_scale) if self.vega is not None else None

    @property
    def price_time_read(self) -> PriceTimeRead:
        return build_price_time_read(
            position_delta=self.position_delta_share_equivalent,
            position_gamma=self.position_gamma_delta_change_per_dollar,
            theta_per_day=(
                max(
                    Decimal("0"),
                    -(self.theta_per_share or Decimal("0")) * self.position_scale,
                )
                if self.can_close_or_roll and self.theta_per_share is not None
                else None
            ),
            current_underlying_price=self.underlying_price,
            previous_close=self.underlying_previous_close,
            weekly_reference_price=self.underlying_week_reference_price,
        )


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
    quote_session: QuoteSession = QuoteSession.UNKNOWN
    quote_evaluated_at: datetime | None = None

    @property
    def open_put_contracts(self) -> int:
        return sum(put.contracts for put in self.puts)

    @property
    def is_prior_session_quote(self) -> bool:
        return self.quote_session.is_prior_session

    @property
    def quote_stamp(self) -> str | None:
        """Absolute Eastern stamp for the last print, or nothing when unclocked."""

        if self.quote_observed_at is None:
            return None
        return quote_session_stamp(
            self.quote_observed_at,
            evaluated_at=self.quote_evaluated_at,
        )

    @property
    def session_move_label(self) -> str:
        """Caption for the move cell, which must never read ``DAY`` for old tape.

        Labelling a Friday close as ``DAY`` on Monday morning was the exact
        failure this replaces: the number was defensible, the caption was not.
        """

        if not self.is_prior_session_quote or self.quote_observed_at is None:
            return "DAY"
        day = market_day_label(self.quote_observed_at, evaluated_at=self.quote_evaluated_at)
        return f"{day} CLOSE"

    @property
    def total_open_mark_profit_loss(self) -> Decimal:
        return self.open_mark_profit_loss + sum(
            (put.open_profit_loss or Decimal("0") for put in self.puts),
            Decimal("0"),
        )

    @property
    def estimated_option_theta_per_day(self) -> Decimal:
        return self.estimated_theta_per_day + self.estimated_put_theta_per_day

    @property
    def price_time_read(self) -> PriceTimeRead | None:
        return aggregate_price_time_reads(
            tuple(
                option.price_time_read
                for option in (*self.calls, *self.puts)
                if option.can_close_or_roll
            )
        )


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
    def price_time_read(self) -> PriceTimeRead | None:
        return aggregate_price_time_reads(
            tuple(
                option.price_time_read
                for option in (*self.calls, *self.puts)
                if option.can_close_or_roll
            )
        )

    @property
    def estimated_put_theta_per_day(self) -> Decimal:
        return sum(
            (
                -(put.theta_per_share or Decimal("0"))
                * put.contract_multiplier
                * Decimal(put.contracts)
                for put in self.puts
                if put.can_close_or_roll
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
    portfolio_delta: Decimal | None
    daily_theta: Decimal
    short_contracts: int
    next_expiration: date | None
    largest_position_percent: Decimal
    open_campaigns: int


@dataclass(frozen=True, slots=True)
class OpenPremiumPace:
    """Opening credits normalized across each live short lot's original term."""

    daily_pace: Decimal | None
    opening_credit: Decimal
    weighted_term_days: Decimal | None
    timed_contracts: int
    total_contracts: int

    @property
    def is_complete(self) -> bool:
        return self.total_contracts > 0 and self.timed_contracts == self.total_contracts


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
    recent_option_activity: Sequence[RecentOptionActivityItem] = ()
    option_outcomes: OptionOutcomeSummary | None = None
    open_premium_pace: OpenPremiumPace | None = None

    @property
    def is_demo(self) -> bool:
        return self.mode == "demo"

    @property
    def prior_session_quote_symbols(self) -> tuple[str, ...]:
        """Live names still priced from an earlier session than this read.

        The header can report a sync that genuinely succeeded while individual
        names carry older tape, so it needs the roster of laggards rather than
        just the job's exit status.
        """

        book = self.live_position_book
        if book is None:
            return ()
        return tuple(item.symbol for item in book.underlyings if item.is_prior_session_quote)
