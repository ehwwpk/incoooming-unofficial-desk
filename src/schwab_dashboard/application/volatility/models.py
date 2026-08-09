from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from schwab_dashboard.domain.analytics import CalculationContext
from schwab_dashboard.domain.validation import (
    require_aware,
    require_non_negative,
    require_text,
)


@dataclass(frozen=True, slots=True)
class DailyVolatilityObservation:
    source_id: str
    session_date: date
    observed_at: datetime
    close: Decimal
    normalized_implied_volatility: Decimal | None = None

    def __post_init__(self) -> None:
        require_text(self.source_id, "source_id")
        require_aware(self.observed_at, "observed_at")
        if self.close <= 0:
            raise ValueError("close must be positive")
        if self.normalized_implied_volatility is not None:
            require_non_negative(
                self.normalized_implied_volatility,
                "normalized_implied_volatility",
            )


@dataclass(frozen=True, slots=True)
class VolatilitySummary:
    observation_count: int
    return_count: int
    annualized_realized_volatility: Decimal | None
    latest_implied_volatility: Decimal | None
    implied_volatility_rank_percent: Decimal | None
    implied_volatility_percentile: Decimal | None
    implied_minus_realized: Decimal | None
    context: CalculationContext
