from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date as Date
from datetime import datetime
from decimal import Decimal

from schwab_dashboard.application.market_time import OptionSessionState
from schwab_dashboard.application.risk.price_time import PriceTimeRead


@dataclass(frozen=True, slots=True)
class PricePoint:
    date: Date
    label: str
    price: Decimal
    x_percent: Decimal
    y_percent: Decimal
    is_friday: bool


@dataclass(frozen=True, slots=True)
class PriceEvent:
    sequence: int
    lifecycle_id: int
    record_id: str
    campaign_id: str
    date: Date
    occurred_at: datetime | None
    time_precision: str
    label: str
    event_type: str
    glyph: str
    detail: str
    price: Decimal
    x_percent: Decimal
    y_percent: Decimal
    vertical_offset: int
    linked_sale_sequence: int | None
    linked_resolution_sequence: int | None
    resolved_on: Date | None
    underlying_at_resolution: Decimal | None
    expires_on: Date
    contracts: int
    strike: Decimal
    underlying_at_sale: Decimal
    strike_upside_percent: Decimal
    entry_days_to_expiration: int
    premium_per_share: Decimal
    gross_premium: Decimal
    buyback_cost: Decimal
    net_cash: Decimal
    outcome: str
    option_value_per_share: Decimal | None
    option_value_vs_credit_percent: Decimal | None
    campaign_label: str = ""
    campaign_confidence: str = "unknown"
    campaign_leg_index: int = 1
    campaign_net_cash: Decimal = Decimal("0")
    option_side: str = "call"
    campaign_slot: int = 0
    campaign_is_first_visible: bool = False
    campaign_is_latest_visible: bool = False


@dataclass(frozen=True, slots=True)
class ShareTradeEvent:
    date: Date
    label: str
    action: str
    glyph: str
    shares: int
    price: Decimal
    x_percent: Decimal
    y_percent: Decimal
    gross_buys: int = 0
    gross_sells: int = 0


@dataclass(frozen=True, slots=True)
class UnderlyingPerformanceWindow:
    key: str
    option_cash: Decimal
    dividends: Decimal
    total_cash: Decimal
    gross_premium: Decimal
    buyback_cost: Decimal
    option_apr: Decimal
    total_cash_apr: Decimal
    premium_capture_percent: Decimal


@dataclass(frozen=True, slots=True)
class RollQuoteCandidate:
    """One quoted contract that could replace an open short option."""

    expires_on: Date
    strike: Decimal
    sell_bid_per_share: Decimal
    quote_source: str
    option_symbol: str = ""
    spread_percent: Decimal | None = None
    open_interest: int | None = None
    volume: int | None = None
    theta_per_share: Decimal | None = None
    quote_observed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class OpenCallClock:
    record_id: str
    campaign_id: str
    campaign_label: str
    policy_id: str
    sold_on: Date
    expires_on: Date
    strike: Decimal
    contracts: int
    underlying_at_sale: Decimal
    close_ask_per_share: Decimal
    bid_per_share: Decimal
    spread_per_share: Decimal
    spread_percent_of_mark: Decimal
    quote_observed_on: Date | None
    quote_status: str
    implied_volatility_percent: Decimal | None
    delta: Decimal | None
    gamma: Decimal | None
    vega: Decimal | None
    volume: int | None
    open_interest: int | None
    roll_quote_candidates: tuple[RollQuoteCandidate, ...]
    original_days_to_expiration: int
    elapsed_days: int
    elapsed_time_percent: Decimal
    days_to_expiration: int
    strike_distance_per_share: Decimal
    strike_distance_percent: Decimal
    mark_per_share: Decimal
    entry_credit_per_share: Decimal
    entry_credit: Decimal
    current_option_value: Decimal
    open_profit_loss: Decimal
    credit_capture_percent: Decimal
    option_value_vs_credit_percent: Decimal
    intrinsic_value: Decimal
    remaining_extrinsic_value: Decimal
    theta_per_share: Decimal
    short_theta_per_day: Decimal
    theta_decay_percent_of_extrinsic: Decimal
    theta_days_of_time_value: Decimal
    time_remaining_percent: Decimal
    decay_stage: str
    session_state: OptionSessionState = OptionSessionState.ACTIVE
    contract_multiplier: Decimal = Decimal("100")
    price_time_read: PriceTimeRead | None = None
    quote_observed_at: datetime | None = None

    @property
    def can_close_or_roll(self) -> bool:
        return self.session_state.can_close_or_roll

    @property
    def session_label(self) -> str:
        return self.session_state.label

    @property
    def position_scale(self) -> Decimal:
        return abs(self.contract_multiplier) * Decimal(self.contracts)

    @property
    def obligated_shares(self) -> int:
        return int(self.position_scale)

    @property
    def position_delta_share_equivalent(self) -> Decimal | None:
        """Current short-call price exposure expressed as equivalent shares."""

        return -(self.delta * self.position_scale) if self.delta is not None else None

    @property
    def position_gamma_delta_change_per_dollar(self) -> Decimal | None:
        return -(self.gamma * self.position_scale) if self.gamma is not None else None

    @property
    def position_vega_per_volatility_point(self) -> Decimal | None:
        return -(self.vega * self.position_scale) if self.vega is not None else None


@dataclass(frozen=True, slots=True)
class CallSaleRecord:
    record_id: str
    campaign_id: str
    parent_record_id: str | None
    policy_id: str
    symbol: str
    sold_on: Date
    expires_on: Date
    contracts: int
    underlying_at_sale: Decimal
    strike: Decimal
    strike_upside_percent: Decimal
    days_to_expiration: int
    premium_per_share: Decimal
    gross_premium: Decimal
    buyback_cost: Decimal
    net_cash: Decimal
    outcome: str
    sale_signal: str
    closed_on: Date | None
    fees: Decimal
    option_side: str = "CALL"


@dataclass(frozen=True, slots=True)
class UnderlyingCallStats:
    symbol: str
    company_name: str
    shares: int
    average_cost: Decimal
    current_price: Decimal
    market_value: Decimal
    unrealized_profit_loss: Decimal
    contract_capacity: int
    active_contracts: int
    coverage_percent: Decimal
    call_tickets: int
    contracts_sold: int
    expired_contracts: int
    closed_contracts: int
    rolled_contracts: int
    assigned_contracts: int
    called_away_shares: int
    gross_premium: Decimal
    buyback_cost: Decimal
    net_option_cash: Decimal
    realized_option_income: Decimal
    open_call_credit: Decimal
    quarter_dividends: Decimal
    quarter_total_cash: Decimal
    quarter_option_apr: Decimal
    quarter_total_cash_apr: Decimal
    average_open_call_iv_percent: Decimal
    average_open_call_delta: Decimal
    current_strike_buffer_percent: Decimal
    next_ex_dividend_date: Date | None
    dividend_per_share: Decimal
    dividend_overlap_contracts: int
    premium_capture_percent: Decimal
    lifetime_option_income: Decimal
    lifetime_dividends: Decimal
    income_adjusted_basis: Decimal
    income_adjusted_basis_per_share: Decimal
    basis_offset_percent: Decimal
    average_strike_upside_percent: Decimal
    average_days_to_expiration: Decimal
    win_rate: Decimal
    performance_windows: Sequence[UnderlyingPerformanceWindow]
    open_call_clocks: Sequence[OpenCallClock]
    thirteen_week_low: Decimal
    thirteen_week_mid: Decimal
    thirteen_week_high: Decimal
    thirteen_week_change_percent: Decimal
    range_position_percent: Decimal
    distance_from_high_percent: Decimal
    price_points: Sequence[PricePoint]
    price_events: Sequence[PriceEvent]
    share_trade_events: Sequence[ShareTradeEvent]
    tone: str
    current_session_change_percent: Decimal | None = None
    current_week_change_percent: Decimal | None = None
    acquired_shares: int = 0

    @property
    def open_call_theta_per_day(self) -> Decimal:
        """Current theoretical daily decay across this name's open short calls."""
        return sum(
            (call.short_theta_per_day for call in self.open_call_clocks),
            Decimal("0"),
        )

    @property
    def daily_price_change_percent(self) -> Decimal | None:
        """Current-session return, falling back to the latest daily closes."""
        if self.current_session_change_percent is not None:
            return self.current_session_change_percent
        return _session_price_change(self.price_points, sessions=1)

    @property
    def weekly_price_change_percent(self) -> Decimal | None:
        """Current five-session return, falling back to the latest daily closes."""
        if self.current_week_change_percent is not None:
            return self.current_week_change_percent
        return _session_price_change(self.price_points, sessions=5)


def _session_price_change(
    points: Sequence[PricePoint],
    *,
    sessions: int,
) -> Decimal | None:
    """Return the verified close-to-close move for a market-session horizon."""
    if sessions <= 0:
        raise ValueError("sessions must be positive")
    if len(points) <= sessions:
        return None
    start = points[-(sessions + 1)].price
    end = points[-1].price
    return (end / start - Decimal("1")) * Decimal("100") if start else None


@dataclass(frozen=True, slots=True)
class CoveredCallPortfolioSummary:
    total_shares: int
    contract_capacity: int
    active_contracts: int
    coverage_percent: Decimal
    call_tickets: int
    contracts_sold: int
    expired_contracts: int
    closed_contracts: int
    rolled_contracts: int
    assigned_contracts: int
    called_away_shares: int
    gross_premium: Decimal
    buyback_cost: Decimal
    net_option_cash: Decimal
    realized_option_income: Decimal
    open_call_credit: Decimal
    open_call_mark_value: Decimal
    open_mark_profit_loss: Decimal
    dividends: Decimal
    total_cash_income: Decimal
    win_rate: Decimal
    annualized_option_yield: Decimal
    annualized_total_cash_yield: Decimal
    premium_capture_percent: Decimal
