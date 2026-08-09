from __future__ import annotations

from decimal import Decimal

from schwab_dashboard.application.attribution.models import (
    PeriodAttribution,
    PeriodAttributionInput,
)
from schwab_dashboard.domain.analytics import CalculationContext, ValueStatus

ONE_HUNDRED = Decimal("100")


def attribute_period(item: PeriodAttributionInput) -> PeriodAttribution:
    option_overlay = (
        item.realized_option_profit_loss + item.open_option_mark_profit_loss_change - item.fees
    )
    actual_total = item.actual_underlying_change + item.actual_dividends + option_overlay
    stock_only_total = item.stock_only_underlying_change + item.stock_only_dividends
    gap = actual_total - stock_only_total
    dividend_difference = item.actual_dividends - item.stock_only_dividends
    underlying_path_difference = item.actual_underlying_change - item.stock_only_underlying_change
    reconstructed_gap = option_overlay + dividend_difference + underlying_path_difference
    if reconstructed_gap != gap:
        raise ArithmeticError("attribution components do not reconcile")

    return PeriodAttribution(
        actual_total=actual_total,
        stock_only_total=stock_only_total,
        actual_minus_stock_only=gap,
        option_overlay_economics=option_overlay,
        dividend_difference=dividend_difference,
        underlying_path_difference=underlying_path_difference,
        actual_return_percent=_return_percent(actual_total, item.average_capital),
        stock_only_return_percent=_return_percent(stock_only_total, item.average_capital),
        context=CalculationContext(
            as_of=item.as_of,
            status=ValueStatus.DERIVED,
            method="covered-overlay-period-attribution",
            method_version="1.0.0",
            source_ids=(item.period_key,),
        ),
    )


def _return_percent(result: Decimal, capital: Decimal | None) -> Decimal | None:
    return result / capital * ONE_HUNDRED if capital is not None else None
