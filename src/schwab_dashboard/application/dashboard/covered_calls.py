from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PricePoint:
    label: str
    price: Decimal
    height_percent: int
    call_sale: bool


@dataclass(frozen=True, slots=True)
class CallSaleRecord:
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
    called_away_shares: int
    gross_premium: Decimal
    buyback_cost: Decimal
    net_option_cash: Decimal
    realized_option_income: Decimal
    open_call_credit: Decimal
    average_strike_upside_percent: Decimal
    average_days_to_expiration: Decimal
    win_rate: Decimal
    current_calls: Sequence[str]
    price_points: Sequence[PricePoint]
    tone: str


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
    called_away_shares: int
    gross_premium: Decimal
    buyback_cost: Decimal
    net_option_cash: Decimal
    realized_option_income: Decimal
    open_call_credit: Decimal
    dividends: Decimal
    total_cash_income: Decimal
    win_rate: Decimal
    annualized_option_yield: Decimal
