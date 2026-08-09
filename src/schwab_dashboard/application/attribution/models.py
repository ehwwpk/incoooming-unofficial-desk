from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from schwab_dashboard.domain.analytics import CalculationContext
from schwab_dashboard.domain.validation import require_aware, require_non_negative


@dataclass(frozen=True, slots=True)
class PeriodAttributionInput:
    period_key: str
    as_of: datetime
    actual_underlying_change: Decimal
    actual_dividends: Decimal
    realized_option_profit_loss: Decimal
    open_option_mark_profit_loss_change: Decimal
    fees: Decimal
    stock_only_underlying_change: Decimal
    stock_only_dividends: Decimal
    average_capital: Decimal | None = None

    def __post_init__(self) -> None:
        require_aware(self.as_of, "as_of")
        require_non_negative(self.fees, "fees")
        if self.average_capital is not None and self.average_capital <= 0:
            raise ValueError("average_capital must be positive when supplied")


@dataclass(frozen=True, slots=True)
class PeriodAttribution:
    actual_total: Decimal
    stock_only_total: Decimal
    actual_minus_stock_only: Decimal
    option_overlay_economics: Decimal
    dividend_difference: Decimal
    underlying_path_difference: Decimal
    actual_return_percent: Decimal | None
    stock_only_return_percent: Decimal | None
    context: CalculationContext
