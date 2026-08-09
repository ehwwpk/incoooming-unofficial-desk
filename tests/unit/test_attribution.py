from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from schwab_dashboard.application.attribution.calculate import attribute_period
from schwab_dashboard.application.attribution.models import PeriodAttributionInput
from schwab_dashboard.domain.analytics import ValueStatus


def test_period_attribution_reconciles_actual_and_stock_only_gap() -> None:
    result = attribute_period(
        PeriodAttributionInput(
            period_key="2026-07",
            as_of=datetime(2026, 8, 1, tzinfo=UTC),
            actual_underlying_change=Decimal("1800"),
            actual_dividends=Decimal("200"),
            realized_option_profit_loss=Decimal("1900"),
            open_option_mark_profit_loss_change=Decimal("-350"),
            fees=Decimal("50"),
            stock_only_underlying_change=Decimal("2700"),
            stock_only_dividends=Decimal("260"),
            average_capital=Decimal("200000"),
        )
    )

    assert result.option_overlay_economics == Decimal("1500")
    assert result.actual_total == Decimal("3500")
    assert result.stock_only_total == Decimal("2960")
    assert result.actual_minus_stock_only == Decimal("540")
    assert (
        result.option_overlay_economics
        + result.dividend_difference
        + result.underlying_path_difference
        == result.actual_minus_stock_only
    )
    assert result.actual_return_percent == Decimal("1.7500")
    assert result.context.status is ValueStatus.DERIVED
