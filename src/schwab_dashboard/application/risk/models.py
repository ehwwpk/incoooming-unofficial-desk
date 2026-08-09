from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from schwab_dashboard.domain.analytics import CalculationContext
from schwab_dashboard.domain.market import QuoteQuality
from schwab_dashboard.domain.validation import (
    require_aware,
    require_non_negative,
    require_optional_non_negative,
    require_text,
)


@dataclass(frozen=True, slots=True)
class OpenCallRiskInput:
    contract_key: str
    symbol: str
    contracts_short: Decimal
    premium_multiplier: Decimal
    deliverable_share_quantity: Decimal
    strike: Decimal
    underlying_price: Decimal
    observed_at: datetime
    quote_quality: QuoteQuality
    entry_credit: Decimal | None = None
    option_mark: Decimal | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    delta: Decimal | None = None
    gamma: Decimal | None = None
    theta: Decimal | None = None
    vega: Decimal | None = None

    def __post_init__(self) -> None:
        require_text(self.contract_key, "contract_key")
        require_text(self.symbol, "symbol")
        require_aware(self.observed_at, "observed_at")
        if self.contracts_short <= 0:
            raise ValueError("contracts_short must be positive")
        if self.premium_multiplier <= 0:
            raise ValueError("premium_multiplier must be positive")
        require_non_negative(self.deliverable_share_quantity, "deliverable_share_quantity")
        require_non_negative(self.strike, "strike")
        require_non_negative(self.underlying_price, "underlying_price")
        for name in ("entry_credit", "option_mark", "bid", "ask"):
            require_optional_non_negative(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class OpenCallRiskView:
    contract_key: str
    symbol: str
    obligated_shares: Decimal
    called_away_notional: Decimal
    distance_to_strike: Decimal
    distance_to_strike_percent: Decimal | None
    current_liability: Decimal | None
    open_mark_profit_loss: Decimal | None
    spread_percent_of_mark: Decimal | None
    delta_share_equivalent: Decimal | None
    dollar_delta_for_one_percent_move: Decimal | None
    gamma_per_dollar_squared: Decimal | None
    theta_estimate_per_day: Decimal | None
    vega_per_volatility_point: Decimal | None
    quote_quality: QuoteQuality


@dataclass(frozen=True, slots=True)
class OpenRiskSummary:
    positions: tuple[OpenCallRiskView, ...]
    called_away_notional: Decimal
    obligated_shares: Decimal
    current_liability: Decimal | None
    theta_estimate_per_day: Decimal | None
    dollar_delta_for_one_percent_move: Decimal | None
    delta_coverage_percent: Decimal
    theta_coverage_percent: Decimal
    context: CalculationContext
