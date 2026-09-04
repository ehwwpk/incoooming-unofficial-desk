from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from schwab_dashboard.application.market_time import market_date
from schwab_dashboard.application.performance.models import PerformanceComparison
from schwab_dashboard.application.performance.periods import PerformancePeriod
from schwab_dashboard.application.performance.projection import build_performance_comparison
from schwab_dashboard.application.performance.reconstruction import (
    build_reconstructed_balance_history,
)
from schwab_dashboard.application.performance.sessions import build_market_calendar
from schwab_dashboard.application.ports.analytics import LiveAnalyticsReader


class ReadPerformanceComparison:
    """Rebuild the complete performance spine for one user-selected period."""

    def __init__(
        self,
        *,
        analytics_reader: LiveAnalyticsReader,
        margin_interest_rate_percent: Decimal,
    ) -> None:
        self._analytics_reader = analytics_reader
        self._margin_interest_rate_percent = margin_interest_rate_percent

    def execute(self, period: PerformancePeriod) -> PerformanceComparison:
        balance_history = tuple(self._analytics_reader.list_balance_history())
        position_history = tuple(self._analytics_reader.list_position_history())
        symbols = tuple(
            sorted(
                {str(row.get("symbol") or "").strip().upper() for row in position_history}
                | {"SPY"} - {""}
            )
        )
        daily_bars = tuple(self._analytics_reader.list_daily_bars(symbols=symbols))
        cash_movements = tuple(self._analytics_reader.list_cash_movements())
        executions = tuple(self._analytics_reader.list_executions())
        lifecycle_events = tuple(self._analytics_reader.list_lifecycle_events())
        calculation_balances = _balances_for_period(
            balance_history,
            period=period,
            include_preceding_anchor=True,
        )
        reconstructed_balances = build_reconstructed_balance_history(
            balance_history=calculation_balances,
            position_history=position_history,
            daily_bars=daily_bars,
            executions=executions,
            cash_movements=cash_movements,
            lifecycle_events=lifecycle_events,
            calendar=build_market_calendar(daily_bars),
        )
        filtered_balances = _balances_for_period(reconstructed_balances, period=period)
        return build_performance_comparison(
            balance_history=filtered_balances,
            cash_movements=cash_movements,
            position_history=position_history,
            daily_bars=daily_bars,
            executions=executions,
            lifecycle_events=lifecycle_events,
            margin_interest_rate_percent=self._margin_interest_rate_percent,
        )


def _balances_for_period(
    balance_history: tuple[dict[str, object], ...],
    *,
    period: PerformancePeriod,
    include_preceding_anchor: bool = False,
) -> tuple[dict[str, object], ...]:
    if not balance_history:
        return balance_history
    dated = [_observed_market_date(row) for row in balance_history]
    starts_on = period.starts_on(through=max(dated))
    if starts_on is None:
        return balance_history
    included = tuple(row for row in balance_history if _observed_market_date(row) >= starts_on)
    if not include_preceding_anchor:
        return included
    preceding_dates = [day for day in dated if day < starts_on]
    if not preceding_dates:
        return included
    preceding = max(preceding_dates)
    return tuple(
        row
        for row in balance_history
        if _observed_market_date(row) == preceding or _observed_market_date(row) >= starts_on
    )


def _observed_market_date(row: dict[str, object]) -> date:
    observed_at = row.get("observed_at")
    if not isinstance(observed_at, (date, datetime)):
        raise ValueError("Balance history row is missing a valid observed_at value.")
    return market_date(observed_at)
