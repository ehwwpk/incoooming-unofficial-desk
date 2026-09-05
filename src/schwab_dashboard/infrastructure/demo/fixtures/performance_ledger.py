from __future__ import annotations

from calendar import monthrange
from dataclasses import replace
from datetime import date
from decimal import Decimal

from schwab_dashboard.application.dashboard.cashflows import build_call_cash_events, cash_total
from schwab_dashboard.application.dashboard.performance import (
    MonthlyPerformanceSummary,
    QuarterPerformanceSummary,
)
from schwab_dashboard.infrastructure.demo.fixtures.call_history import build_call_history
from schwab_dashboard.infrastructure.demo.fixtures.cash_events import build_dividend_cash_events
from schwab_dashboard.infrastructure.demo.fixtures.short_puts import build_put_cash_events

D = Decimal


def build_quarter_history() -> tuple[QuarterPerformanceSummary, ...]:
    rows = (
        ("Q3 '25", D("6200"), D("800")),
        ("Q4 '25", D("6400"), D("950")),
        ("Q1 '26", D("9800"), D("1050")),
        ("Q2 '26", D("10505"), D("1120")),
    )
    maximum = max(option_cash + dividends for _, option_cash, dividends in rows)
    return tuple(
        QuarterPerformanceSummary(
            label=label,
            option_cash=option_cash,
            dividends=dividends,
            total_cash=option_cash + dividends,
            bar_percent=int((option_cash + dividends) / maximum * 100),
        )
        for label, option_cash, dividends in rows
    )


def build_monthly_performance() -> tuple[MonthlyPerformanceSummary, ...]:
    """Return a calendar ledger whose recent months reconcile to executions."""

    rows = (
        ("JAN", 2026, "2400", "300", "0", "0", 0, "0", "176000", False),
        ("FEB", 2026, "1900", "200", "0", "0", 0, "0", "179000", False),
        ("MAR", 2026, "4100", "800", "0", "1197", 0, "0", "184000", False),
        ("APR", 2026, "3600", "700", "0", "0", 0, "0", "181000", False),
        ("MAY", 2026, "2395", "0", "0", "0", 2, "200", "186000", False),
        ("JUN", 2026, "1750", "0", "0", "1246", 0, "0", "188000", False),
        ("JUL", 2026, "3895", "770", "0", "0", 0, "0", "194000", False),
        ("AUG", 2026, "965", "1895", "0", "0", 0, "0", "206556", True),
    )
    monthly = tuple(_monthly_summary(row) for row in rows)
    records = build_call_history()
    events = (*build_call_cash_events(records), *build_put_cash_events())
    dividends = build_dividend_cash_events()
    result: list[MonthlyPerformanceSummary] = []
    for month, item in enumerate(monthly, start=1):
        if month < 5:
            result.append(item)
            continue
        start = date(item.year, month, 1)
        end = date(item.year, month, monthrange(item.year, month)[1])
        gross = cash_total(events, start=start, end=end, event_types=frozenset({"OPENING CREDIT"}))
        debit = -cash_total(events, start=start, end=end, event_types=frozenset({"CLOSING DEBIT"}))
        fees = -cash_total(events, start=start, end=end, event_types=frozenset({"FEES"}))
        dividend_cash = cash_total(dividends, start=start, end=end)
        net = gross - debit - fees
        result.append(
            replace(
                item,
                gross_premium=gross,
                closing_debits=debit,
                fees=fees,
                option_cash=net,
                dividends=dividend_cash,
                total_cash=net + dividend_cash,
            )
        )
    return tuple(result)


def _monthly_summary(row: tuple[object, ...]) -> MonthlyPerformanceSummary:
    label, year = str(row[0]), int(str(row[1]))
    gross = D(str(row[2]))
    closing_debits = D(str(row[3]))
    fees = D(str(row[4]))
    dividends = D(str(row[5]))
    option_cash = gross - closing_debits - fees
    return MonthlyPerformanceSummary(
        label=label,
        year=year,
        option_cash=option_cash,
        dividends=dividends,
        total_cash=option_cash + dividends,
        gross_premium=gross,
        closing_debits=closing_debits,
        fees=fees,
        assigned_contracts=int(str(row[6])),
        called_away_shares=D(str(row[7])),
        average_covered_capital=D(str(row[8])),
        is_partial=bool(row[9]),
    )
