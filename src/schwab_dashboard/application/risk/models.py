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
class OpenOptionRiskInput:
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
    option_type: str = "CALL"

    def __post_init__(self) -> None:
        require_text(self.contract_key, "contract_key")
        require_text(self.symbol, "symbol")
        require_aware(self.observed_at, "observed_at")
        if self.option_type.upper() not in {"CALL", "PUT"}:
            raise ValueError("option_type must be CALL or PUT")
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
class UnderlyingEquityRiskInput:
    symbol: str
    shares: Decimal
    underlying_price: Decimal

    def __post_init__(self) -> None:
        require_text(self.symbol, "symbol")
        require_non_negative(self.underlying_price, "underlying_price")


@dataclass(frozen=True, slots=True)
class OpenOptionRiskView:
    contract_key: str
    symbol: str
    option_type: str
    contracts_short: Decimal
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
class UnderlyingRiskView:
    symbol: str
    shares: Decimal
    option_contracts: Decimal
    option_delta_share_equivalent: Decimal | None
    net_delta_share_equivalent: Decimal | None
    estimated_value_change_for_one_percent_move: Decimal | None
    theta_estimate_per_day: Decimal | None
    gamma_delta_change_for_one_dollar_move: Decimal | None
    vega_per_volatility_point: Decimal | None
    delta_coverage_percent: Decimal
    theta_coverage_percent: Decimal
    gamma_coverage_percent: Decimal
    vega_coverage_percent: Decimal

    @property
    def greek_coverage_percent(self) -> Decimal:
        return min(
            self.delta_coverage_percent,
            self.theta_coverage_percent,
            self.vega_coverage_percent,
        )

    @property
    def net_share_exposure_percent(self) -> Decimal | None:
        """Share-equivalent exposure retained after the known option deltas."""
        if self.net_delta_share_equivalent is None or self.shares == 0:
            return None
        return self.net_delta_share_equivalent / self.shares * Decimal("100")

    @property
    def iv_point_in_theta_days(self) -> Decimal | None:
        """Absolute one-point vega shock expressed in current theta days."""
        if (
            self.vega_per_volatility_point is None
            or self.theta_estimate_per_day is None
            or self.theta_estimate_per_day == 0
        ):
            return None
        return abs(self.vega_per_volatility_point) / abs(self.theta_estimate_per_day)


@dataclass(frozen=True, slots=True)
class OpenRiskSummary:
    positions: tuple[OpenOptionRiskView, ...]
    underlyings: tuple[UnderlyingRiskView, ...]
    called_away_notional: Decimal
    obligated_shares: Decimal
    current_liability: Decimal | None
    theta_estimate_per_day: Decimal | None
    dollar_delta_for_one_percent_move: Decimal | None
    estimated_value_change_for_one_percent_move: Decimal | None
    option_delta_share_equivalent: Decimal | None
    net_delta_share_equivalent: Decimal | None
    gamma_delta_change_for_one_dollar_move: Decimal | None
    vega_per_volatility_point: Decimal | None
    delta_coverage_percent: Decimal
    theta_coverage_percent: Decimal
    gamma_coverage_percent: Decimal
    vega_coverage_percent: Decimal
    quote_coverage_percent: Decimal
    oldest_quote_at: datetime
    newest_quote_at: datetime
    context: CalculationContext

    @property
    def greek_coverage_percent(self) -> Decimal:
        """Conservative coverage across the three primary risk sensitivities."""
        return min(
            self.delta_coverage_percent,
            self.theta_coverage_percent,
            self.vega_coverage_percent,
        )

    @property
    def net_share_exposure_percent(self) -> Decimal | None:
        """Book net delta as a percentage of the shares currently held."""
        held_shares = sum((row.shares for row in self.underlyings), Decimal(0))
        if self.net_delta_share_equivalent is None or held_shares == 0:
            return None
        return self.net_delta_share_equivalent / held_shares * Decimal("100")

    @property
    def iv_point_in_theta_days(self) -> Decimal | None:
        """Absolute one-point vega shock expressed in current theta days."""
        if (
            self.vega_per_volatility_point is None
            or self.theta_estimate_per_day is None
            or self.theta_estimate_per_day == 0
        ):
            return None
        return abs(self.vega_per_volatility_point) / abs(self.theta_estimate_per_day)

    @property
    def largest_absolute_vega_symbol(self) -> str | None:
        """Name whose open options have the largest modeled IV sensitivity."""
        covered = tuple(
            row for row in self.underlyings if row.vega_per_volatility_point is not None
        )
        if not covered:
            return None
        return max(
            covered,
            key=lambda row: abs(
                row.vega_per_volatility_point
                if row.vega_per_volatility_point is not None
                else Decimal(0)
            ),
        ).symbol


# Compatibility aliases for callers written while the book was call-only.
OpenCallRiskInput = OpenOptionRiskInput
OpenCallRiskView = OpenOptionRiskView
