from __future__ import annotations

from calendar import month_abbr
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from statistics import median

from schwab_dashboard.application.dashboard.covered_calls import CoveredCallPortfolioSummary
from schwab_dashboard.application.dashboard.live_cash_series import (
    build_live_cash_chart_series,
)
from schwab_dashboard.application.dashboard.models import (
    IncomePeriod,
    IncomeSummary,
    LivePositionBook,
)
from schwab_dashboard.application.dashboard.option_activity import count_rolled_contracts
from schwab_dashboard.application.dashboard.performance import (
    CashActivityItem,
    CashActivityWindow,
    CashChartSeries,
    MonthlyPerformanceSummary,
    OperatorMetricsSummary,
    PerformanceWindowSummary,
)
from schwab_dashboard.application.dashboard.short_premium import (
    is_closing_buy as _is_closing_buy,
)
from schwab_dashboard.application.dashboard.short_premium import (
    is_opening_sale as _is_opening_sale,
)
from schwab_dashboard.application.dashboard.short_premium import (
    is_short_premium_execution,
    option_cash_action_label,
)
from schwab_dashboard.application.market_time import ledger_market_date
from schwab_dashboard.application.option_lifecycle import (
    delivered_shares,
    lifecycle_event_type,
    option_contracts,
    option_side,
)
from schwab_dashboard.application.values import sum_if_complete

ZERO = Decimal("0")
HUNDRED = Decimal("100")
MONTH_DAYS = Decimal("30.4375")


@dataclass(frozen=True, slots=True)
class LivePerformanceProjection:
    income: IncomeSummary
    income_periods: tuple[IncomePeriod, ...]
    performance_windows: tuple[PerformanceWindowSummary, ...]
    monthly_performance: tuple[MonthlyPerformanceSummary, ...]
    cash_events: tuple[CashActivityItem, ...]
    cash_activity_windows: tuple[CashActivityWindow, ...]
    cash_chart_series: tuple[CashChartSeries, ...]
    covered_calls: CoveredCallPortfolioSummary
    operator_metrics: OperatorMetricsSummary


def build_live_performance(
    *,
    executions: Sequence[Mapping[str, object]],
    cash_movements: Sequence[Mapping[str, object]],
    lifecycle_events: Sequence[Mapping[str, object]],
    live_book: LivePositionBook,
    covered_capital: Decimal | None,
    as_of: date,
) -> LivePerformanceProjection:
    option_executions = tuple(row for row in executions if is_short_premium_execution(row))
    dividends = tuple(
        row
        for row in cash_movements
        if str(row.get("movement_type") or "").strip().casefold().split(".")[-1] == "dividend"
    )
    assignments = tuple(
        row
        for row in lifecycle_events
        if lifecycle_event_type(row.get("event_type")) == "assignment"
    )
    call_assignments = tuple(
        row for row in assignments if option_side(row.get("option_side")) == "call"
    )
    put_assignments = tuple(
        row for row in assignments if option_side(row.get("option_side")) == "put"
    )
    expirations = tuple(
        row
        for row in lifecycle_events
        if lifecycle_event_type(row.get("event_type")) == "expiration"
    )
    windows = tuple(
        _window(
            key=key,
            label=label,
            start=start,
            end=as_of,
            executions=option_executions,
            dividends=dividends,
            lifecycle_events=lifecycle_events,
            covered_capital=covered_capital,
        )
        for key, label, start in (
            ("month", "4W", as_of - timedelta(days=27)),
            ("quarter", "QTR", as_of - timedelta(days=90)),
            ("ytd", "YTD", date(as_of.year, 1, 1)),
            ("r365", "R365", as_of - timedelta(days=364)),
        )
    )
    monthly = _monthly_performance(
        option_executions,
        dividends,
        call_assignments,
        put_assignments,
        covered_capital=covered_capital,
        as_of=as_of,
    )
    cash_events = _cash_events(option_executions, dividends)
    cash_windows = tuple(
        CashActivityWindow(
            key=window.key,
            label=window.label,
            range_label=window.range_label,
            premium_received=window.gross_premium,
            executed_debits=window.buyback_cost,
            dividends=window.dividends,
            net_option_cash=window.option_cash,
            total_strategy_cash=window.total_cash,
            fees=window.fees,
            events=tuple(
                event
                for event in cash_events
                if as_of - timedelta(days=window.days - 1) <= event.occurred_on <= as_of
            )[:3],
        )
        for window in windows
    )
    covered_calls = _covered_call_summary(
        option_executions,
        dividends,
        call_assignments,
        expirations,
        live_book=live_book,
        covered_capital=covered_capital,
        r365=windows[-1],
    )
    operator = _operator_metrics(monthly, windows, covered_calls)
    cash_chart_series = build_live_cash_chart_series(
        executions=option_executions,
        dividends=dividends,
        as_of=as_of,
    )
    return LivePerformanceProjection(
        income=IncomeSummary(
            week=windows[0].option_cash,
            month=windows[0].option_cash,
            quarter=windows[1].option_cash,
            year_to_date=windows[2].total_cash,
            win_rate=covered_calls.win_rate,
            annualized_yield=windows[-1].annualized_option_yield,
        ),
        income_periods=tuple(
            IncomePeriod(
                label=item.label,
                option_income=item.option_cash,
                dividends=item.dividends,
                total=item.total_cash,
                bar_percent=_bar_percent(item.total_cash, monthly),
            )
            for item in monthly
        ),
        performance_windows=windows,
        monthly_performance=monthly,
        cash_events=cash_events,
        cash_activity_windows=cash_windows,
        cash_chart_series=cash_chart_series,
        covered_calls=covered_calls,
        operator_metrics=operator,
    )


def _window(
    *,
    key: str,
    label: str,
    start: date,
    end: date,
    executions: Sequence[Mapping[str, object]],
    dividends: Sequence[Mapping[str, object]],
    lifecycle_events: Sequence[Mapping[str, object]],
    covered_capital: Decimal | None,
) -> PerformanceWindowSummary:
    trades = [row for row in executions if start <= _row_date(row) <= end]
    window_dividends = [row for row in dividends if start <= _row_date(row) <= end]
    lifecycle = [row for row in lifecycle_events if start <= _row_date(row) <= end]
    gross = sum((_gross_credit(row) for row in trades), ZERO)
    buyback = sum((_closing_debit(row) for row in trades), ZERO)
    option_cash = sum((_decimal(row.get("net_cash")) for row in trades), ZERO)
    fees = sum((_decimal(row.get("fees")) for row in trades), ZERO)
    dividend_cash = sum((_decimal(row.get("amount")) for row in window_dividends), ZERO)
    days = (end - start).days + 1
    annual_factor = Decimal("365") / Decimal(days)
    opening = [row for row in trades if _is_opening_sale(row)]
    completed = [row for row in trades if _is_closing_buy(row)] + list(lifecycle)
    return PerformanceWindowSummary(
        key=key,
        label=label,
        range_label=f"{start:%b %d}-{end:%b %d}",
        days=days,
        option_cash=option_cash,
        dividends=dividend_cash,
        total_cash=option_cash + dividend_cash,
        gross_premium=gross,
        buyback_cost=buyback,
        call_tickets=len(opening),
        contracts=sum((int(_decimal(row.get("quantity"))) for row in opening), 0),
        completed_trades=len(completed),
        win_rate=ZERO,
        annualized_option_yield=(
            option_cash / covered_capital * annual_factor * HUNDRED if covered_capital else None
        ),
        annualized_total_yield=(
            (option_cash + dividend_cash) / covered_capital * annual_factor * HUNDRED
            if covered_capital
            else None
        ),
        monthly_option_run_rate=option_cash / Decimal(days) * MONTH_DAYS,
        monthly_total_run_rate=(option_cash + dividend_cash) / Decimal(days) * MONTH_DAYS,
        premium_capture_percent=(option_cash / gross * HUNDRED if gross else ZERO),
        buyback_drag_percent=(buyback / gross * HUNDRED if gross else ZERO),
        fees=fees,
    )


def _monthly_performance(
    executions: Sequence[Mapping[str, object]],
    dividends: Sequence[Mapping[str, object]],
    call_assignments: Sequence[Mapping[str, object]],
    put_assignments: Sequence[Mapping[str, object]],
    *,
    covered_capital: Decimal | None,
    as_of: date,
) -> tuple[MonthlyPerformanceSummary, ...]:
    dated_rows = (*executions, *dividends, *call_assignments, *put_assignments)
    if not dated_rows:
        return ()
    first_observed = min(_row_date(row) for row in dated_rows)
    observed_start_month = date(first_observed.year, first_observed.month, 1)
    first_month = observed_start_month
    rolling_year_start = _month_shift(date(as_of.year, as_of.month, 1), 11)
    first_month = max(first_month, rolling_year_start)
    starts_mid_month = first_month == observed_start_month and first_observed.day > 1
    month_count = (as_of.year - first_month.year) * 12 + as_of.month - first_month.month + 1
    months = [
        _month_shift(date(as_of.year, as_of.month, 1), offset)
        for offset in range(month_count - 1, -1, -1)
    ]
    result: list[MonthlyPerformanceSummary] = []
    for month in months:
        next_month = _month_shift(month, -1)
        month_end = next_month - timedelta(days=1)
        trades = [row for row in executions if month <= _row_date(row) <= month_end]
        month_dividends = [row for row in dividends if month <= _row_date(row) <= month_end]
        month_call_assignments = [
            row for row in call_assignments if month <= _row_date(row) <= month_end
        ]
        month_put_assignments = [
            row for row in put_assignments if month <= _row_date(row) <= month_end
        ]
        gross = sum((_gross_credit(row) for row in trades), ZERO)
        closing = sum((_closing_debit(row) for row in trades), ZERO)
        option_cash = sum((_decimal(row.get("net_cash")) for row in trades), ZERO)
        dividend_cash = sum((_decimal(row.get("amount")) for row in month_dividends), ZERO)
        result.append(
            MonthlyPerformanceSummary(
                label=f"{month_abbr[month.month]} {str(month.year)[2:]}",
                year=month.year,
                option_cash=option_cash,
                dividends=dividend_cash,
                total_cash=option_cash + dividend_cash,
                gross_premium=gross,
                closing_debits=closing,
                fees=sum((_decimal(row.get("fees")) for row in trades), ZERO),
                assigned_contracts=sum(
                    (option_contracts(row) for row in month_call_assignments),
                    0,
                )
                + sum(
                    (option_contracts(row) for row in month_put_assignments),
                    0,
                ),
                called_away_shares=sum(
                    (delivered_shares(row) for row in month_call_assignments), ZERO
                ),
                acquired_shares=sum((delivered_shares(row) for row in month_put_assignments), ZERO),
                average_covered_capital=covered_capital,
                is_partial=month.year == as_of.year and month.month == as_of.month,
                coverage_status=(
                    "coverage_start"
                    if month == first_month and starts_mid_month
                    else "partial"
                    if month.year == as_of.year and month.month == as_of.month
                    else "observed"
                ),
                coverage_note=(
                    f"First normalized cash event {first_observed:%b %d}"
                    if month == first_month and starts_mid_month
                    else ""
                ),
            )
        )
    return tuple(result)


def _cash_events(
    executions: Sequence[Mapping[str, object]],
    dividends: Sequence[Mapping[str, object]],
) -> tuple[CashActivityItem, ...]:
    events: list[CashActivityItem] = []
    for row in executions:
        symbol = str(row.get("underlying_symbol") or row.get("symbol") or "OPTION")
        amount = _decimal(row.get("net_cash"))
        events.append(
            CashActivityItem(
                event_id=str(row["external_key"]),
                occurred_on=_row_date(row),
                symbol=symbol,
                action_label=option_cash_action_label(row),
                amount=amount,
                contracts=int(_decimal(row.get("quantity"))),
                tone="credit" if amount >= ZERO else "debit",
                anchor_id=f"{symbol.lower()}-workspace",
            )
        )
    for row in dividends:
        symbol = str(row.get("symbol") or "PORTFOLIO")
        events.append(
            CashActivityItem(
                event_id=str(row["external_key"]),
                occurred_on=_row_date(row),
                symbol=symbol,
                action_label="DIVIDEND RECEIVED",
                amount=_decimal(row.get("amount")),
                contracts=0,
                tone="dividend",
                anchor_id=f"{symbol.lower()}-workspace",
            )
        )
    return tuple(sorted(events, key=lambda item: (item.occurred_on, item.event_id), reverse=True))


def _covered_call_summary(
    executions: Sequence[Mapping[str, object]],
    dividends: Sequence[Mapping[str, object]],
    assignments: Sequence[Mapping[str, object]],
    expirations: Sequence[Mapping[str, object]],
    *,
    live_book: LivePositionBook,
    covered_capital: Decimal | None,
    r365: PerformanceWindowSummary,
) -> CoveredCallPortfolioSummary:
    openings = [row for row in executions if _is_opening_sale(row)]
    closings = [row for row in executions if _is_closing_buy(row)]
    gross = sum((_gross_credit(row) for row in executions), ZERO)
    buyback = sum((_closing_debit(row) for row in executions), ZERO)
    option_cash = sum((_decimal(row.get("net_cash")) for row in executions), ZERO)
    dividend_cash = sum((_decimal(row.get("amount")) for row in dividends), ZERO)
    options = (*live_book.calls, *live_book.puts)
    open_credit = sum_if_complete(option.entry_credit for option in options)
    open_value = sum_if_complete(option.current_option_value for option in options)
    assigned_contracts = sum((option_contracts(row) for row in assignments), 0)
    return CoveredCallPortfolioSummary(
        total_shares=live_book.total_shares,
        contract_capacity=live_book.contract_capacity,
        active_contracts=live_book.open_call_contracts,
        coverage_percent=live_book.coverage_percent,
        call_tickets=len(openings),
        contracts_sold=sum((int(_decimal(row.get("quantity"))) for row in openings), 0),
        expired_contracts=sum((option_contracts(row) for row in expirations), 0),
        closed_contracts=sum((int(_decimal(row.get("quantity"))) for row in closings), 0),
        rolled_contracts=count_rolled_contracts(executions),
        assigned_contracts=assigned_contracts,
        called_away_shares=sum((delivered_shares(row) for row in assignments), ZERO),
        gross_premium=gross,
        buyback_cost=buyback,
        net_option_cash=option_cash,
        realized_option_income=option_cash,
        open_call_credit=open_credit,
        open_call_mark_value=open_value,
        open_mark_profit_loss=live_book.total_open_mark_profit_loss,
        dividends=dividend_cash,
        total_cash_income=option_cash + dividend_cash,
        win_rate=ZERO,
        annualized_option_yield=r365.annualized_option_yield,
        annualized_total_cash_yield=r365.annualized_total_yield,
        premium_capture_percent=(option_cash / gross * HUNDRED if gross else ZERO),
    )


def _operator_metrics(
    monthly: Sequence[MonthlyPerformanceSummary],
    windows: Sequence[PerformanceWindowSummary],
    covered: CoveredCallPortfolioSummary,
) -> OperatorMetricsSummary:
    full = [
        item for item in monthly if not item.is_partial and item.coverage_status != "coverage_start"
    ]
    option_values = [item.option_cash for item in full]
    latest_three = option_values[-3:]
    return OperatorMetricsSummary(
        rolling_four_week_option_cash=windows[0].option_cash,
        quarter_monthly_run_rate=windows[1].monthly_option_run_rate,
        year_to_date_monthly_run_rate=windows[2].monthly_option_run_rate,
        rolling_year_monthly_average=(
            sum(option_values, ZERO) / Decimal(len(option_values)) if option_values else ZERO
        ),
        rolling_three_month_average=(
            sum(latest_three, ZERO) / Decimal(len(latest_three)) if latest_three else ZERO
        ),
        median_completed_month=(Decimal(str(median(option_values))) if option_values else ZERO),
        best_completed_month=max(option_values, default=ZERO),
        worst_completed_month=min(option_values, default=ZERO),
        completed_months=len(full),
        compliant_call_tickets=0,
        total_call_tickets=covered.call_tickets,
        safe_ticket_pace_monthly=ZERO,
        contract_pace_monthly=ZERO,
        premium_capture_percent=covered.premium_capture_percent,
        buyback_drag_percent=windows[3].buyback_drag_percent,
        average_strike_gap_percent=ZERO,
        average_days_to_expiration=ZERO,
        uncovered_contract_capacity=max(0, covered.contract_capacity - covered.active_contracts),
    )


def _gross_credit(row: Mapping[str, object]) -> Decimal:
    return _decimal(row.get("gross_amount")) if _is_opening_sale(row) else ZERO


def _closing_debit(row: Mapping[str, object]) -> Decimal:
    return _decimal(row.get("gross_amount")) if _is_closing_buy(row) else ZERO


def _row_date(row: Mapping[str, object]) -> date:
    value = row.get("occurred_at")
    if isinstance(value, (date, datetime)):
        return ledger_market_date(value)
    raise ValueError("Ledger row is missing its source date")


def _decimal(value: object) -> Decimal:
    return ZERO if value is None else Decimal(str(value))


def _month_shift(value: date, offset_back: int) -> date:
    total = value.year * 12 + value.month - 1 - offset_back
    return date(total // 12, total % 12 + 1, 1)


def _bar_percent(value: Decimal, months: Sequence[MonthlyPerformanceSummary]) -> int:
    maximum = max((abs(item.total_cash) for item in months), default=ZERO)
    return max(0, int(abs(value) / maximum * HUNDRED)) if maximum else 0
