from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PricePoint:
    date: date
    label: str
    price: Decimal
    x_percent: Decimal
    y_percent: Decimal
    is_friday: bool


@dataclass(frozen=True, slots=True)
class PriceEvent:
    sequence: int
    lifecycle_id: int
    date: date
    label: str
    event_type: str
    glyph: str
    detail: str
    price: Decimal
    x_percent: Decimal
    y_percent: Decimal
    vertical_offset: int
    linked_sale_sequence: int | None


@dataclass(frozen=True, slots=True)
class ShareTradeEvent:
    date: date
    label: str
    action: str
    glyph: str
    shares: int
    price: Decimal
    x_percent: Decimal
    y_percent: Decimal


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
    """One later/higher call quote that could replace an open short call."""

    expires_on: date
    strike: Decimal
    sell_bid_per_share: Decimal
    quote_source: str


@dataclass(frozen=True, slots=True)
class OpenCallClock:
    record_id: str
    campaign_id: str
    policy_id: str
    sold_on: date
    expires_on: date
    strike: Decimal
    contracts: int
    underlying_at_sale: Decimal
    close_ask_per_share: Decimal
    bid_per_share: Decimal
    spread_per_share: Decimal
    spread_percent_of_mark: Decimal
    quote_observed_on: date | None
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


@dataclass(frozen=True, slots=True)
class CallSaleRecord:
    record_id: str
    campaign_id: str
    parent_record_id: str | None
    policy_id: str
    symbol: str
    sold_on: date
    expires_on: date
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
    closed_on: date | None
    fees: Decimal


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
    next_ex_dividend_date: date | None
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

    @property
    def open_call_theta_per_day(self) -> Decimal:
        """Current theoretical daily decay across this name's open short calls."""
        return sum(
            (call.short_theta_per_day for call in self.open_call_clocks),
            Decimal("0"),
        )


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
