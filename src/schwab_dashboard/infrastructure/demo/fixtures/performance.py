from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from schwab_dashboard.application.dashboard.covered_calls import (
    CallSaleRecord,
    CoveredCallPortfolioSummary,
    UnderlyingCallStats,
)
from schwab_dashboard.application.dashboard.performance import (
    BasisLensSummary,
    ManagementObjectiveSummary,
    PerformanceWindowSummary,
    QuarterPerformanceSummary,
    calculate_capital_recovery,
)

D = Decimal
ZERO = D("0")
MONEY = D("0.01")
TENTH = D("0.1")
YEAR_DAYS = D("365")
MONTH_DAYS = YEAR_DAYS / D("12")
MONTHLY_TARGET = D("3000")


def build_performance_windows(
    covered_calls: CoveredCallPortfolioSummary,
    stock_value: Decimal,
) -> tuple[PerformanceWindowSummary, ...]:
    rows = (
        ("week", "WEEK", "Aug 01 - Aug 07", 7, "80", "0", "965", "885", 2, 7, 2, 1),
        ("month", "4 WEEKS", "Jul 11 - Aug 07", 28, "1950", "0", "3390", "1440", 5, 18, 4, 3),
        (
            "quarter",
            "13 WEEKS",
            "May 15 - Aug 07",
            85,
            str(covered_calls.net_option_cash),
            str(covered_calls.dividends),
            str(covered_calls.gross_premium),
            str(covered_calls.buyback_cost),
            covered_calls.call_tickets,
            covered_calls.contracts_sold,
            11,
            10,
        ),
        (
            "ytd",
            "CALENDAR YTD",
            "Jan 01 - Aug 07",
            219,
            "21880",
            "3416",
            "31950",
            "10070",
            54,
            185,
            44,
            39,
        ),
        (
            "r365",
            "ROLLING 365",
            "Aug 08, 2025 - Aug 07, 2026",
            365,
            "31780",
            "5236",
            "48250",
            "16470",
            82,
            278,
            68,
            59,
        ),
    )
    return tuple(_window(row, stock_value) for row in rows)


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


def build_objective_summary(
    records: Sequence[CallSaleRecord],
    covered_calls: CoveredCallPortfolioSummary,
    windows: Sequence[PerformanceWindowSummary],
) -> ManagementObjectiveSummary:
    by_key = {window.key: window for window in windows}
    total_contracts = sum(record.contracts for record in records)
    compliant = sum(
        1
        for record in records
        if D("15") <= record.strike_upside_percent <= D("40")
        and 21 <= record.days_to_expiration <= 56
    )
    weighted_gap = (
        sum((record.strike_upside_percent * record.contracts for record in records), ZERO)
        / total_contracts
    )
    weighted_dte = (
        D(sum(record.days_to_expiration * record.contracts for record in records)) / total_contracts
    )
    rolling_average = by_key["r365"].monthly_option_run_rate
    monthly_results = tuple(
        D(value)
        for value in (
            "1095",
            "2300",
            "2600",
            "2100",
            "1700",
            "3300",
            "2900",
            "3600",
            "3100",
            "5035",
            "2370",
            "1680",
        )
    )
    return ManagementObjectiveSummary(
        monthly_option_target=MONTHLY_TARGET,
        rolling_four_week_option_cash=by_key["month"].option_cash,
        quarter_monthly_run_rate=by_key["quarter"].monthly_option_run_rate,
        year_to_date_monthly_run_rate=by_key["ytd"].monthly_option_run_rate,
        rolling_year_monthly_average=rolling_average,
        rolling_year_target_gap=MONTHLY_TARGET - rolling_average,
        rolling_year_target_progress_percent=(rolling_average / MONTHLY_TARGET * 100).quantize(
            TENTH
        ),
        target_months_hit=sum(1 for result in monthly_results if result >= MONTHLY_TARGET),
        observed_months=len(monthly_results),
        compliant_call_tickets=compliant,
        total_call_tickets=len(records),
        safe_ticket_pace_monthly=(D(len(records)) * MONTH_DAYS / D("85")).quantize(TENTH),
        contract_pace_monthly=(D(total_contracts) * MONTH_DAYS / D("85")).quantize(TENTH),
        premium_capture_percent=(
            covered_calls.net_option_cash / covered_calls.gross_premium * 100
        ).quantize(TENTH),
        buyback_drag_percent=(
            covered_calls.buyback_cost / covered_calls.gross_premium * 100
        ).quantize(TENTH),
        average_strike_gap_percent=weighted_gap.quantize(TENTH),
        average_days_to_expiration=weighted_dte.quantize(TENTH),
        uncovered_contract_capacity=(
            covered_calls.contract_capacity - covered_calls.active_contracts
        ),
        monthly_option_results=monthly_results,
    )


def build_basis_lens(
    underlyings: Sequence[UnderlyingCallStats],
) -> tuple[BasisLensSummary, ...]:
    items = tuple(_basis_item(item) for item in underlyings)
    original = sum((item.original_cost_basis for item in items), ZERO)
    option_income = sum((item.lifetime_option_income for item in items), ZERO)
    dividends = sum((item.lifetime_dividends for item in items), ZERO)
    management_income = option_income + dividends
    recovery = calculate_capital_recovery(original, management_income)
    portfolio = BasisLensSummary(
        symbol="PORT",
        original_cost_basis=original,
        lifetime_option_income=option_income,
        lifetime_dividends=dividends,
        lifetime_management_income=management_income,
        income_adjusted_basis=recovery.income_adjusted_basis,
        income_adjusted_basis_per_share=None,
        basis_offset_percent=recovery.recovered_percent,
        capital_remaining=recovery.capital_remaining,
        recovery_surplus=recovery.recovery_surplus,
        fully_recovered=recovery.fully_recovered,
    )
    return (portfolio, *items)


def _window(row: tuple[object, ...], stock_value: Decimal) -> PerformanceWindowSummary:
    key, label, range_label = str(row[0]), str(row[1]), str(row[2])
    days = int(str(row[3]))
    tickets = int(str(row[8]))
    contracts = int(str(row[9]))
    completed = int(str(row[10]))
    wins = int(str(row[11]))
    option_cash, dividends = D(str(row[4])), D(str(row[5]))
    gross_premium, buyback_cost = D(str(row[6])), D(str(row[7]))
    annual_factor = YEAR_DAYS / D(days)
    monthly_run_rate = (option_cash * MONTH_DAYS / D(days)).quantize(MONEY)
    monthly_total_run_rate = ((option_cash + dividends) * MONTH_DAYS / D(days)).quantize(MONEY)
    target_for_window = (MONTHLY_TARGET * D(days) / MONTH_DAYS).quantize(MONEY)
    return PerformanceWindowSummary(
        key=key,
        label=label,
        range_label=range_label,
        days=days,
        option_cash=option_cash,
        dividends=dividends,
        total_cash=option_cash + dividends,
        gross_premium=gross_premium,
        buyback_cost=buyback_cost,
        call_tickets=tickets,
        contracts=contracts,
        completed_trades=completed,
        win_rate=(D(wins) / D(completed) * 100).quantize(TENTH) if completed else ZERO,
        annualized_option_yield=(option_cash / stock_value * annual_factor * 100).quantize(TENTH),
        annualized_total_yield=(
            (option_cash + dividends) / stock_value * annual_factor * 100
        ).quantize(TENTH),
        monthly_option_run_rate=monthly_run_rate,
        monthly_total_run_rate=monthly_total_run_rate,
        target_cash_for_window=target_for_window,
        target_progress_percent=max(ZERO, monthly_run_rate / MONTHLY_TARGET * 100).quantize(TENTH),
        premium_capture_percent=(option_cash / gross_premium * 100).quantize(TENTH)
        if gross_premium
        else ZERO,
        buyback_drag_percent=(buyback_cost / gross_premium * 100).quantize(TENTH)
        if gross_premium
        else ZERO,
    )


def _basis_item(underlying: UnderlyingCallStats) -> BasisLensSummary:
    original = underlying.average_cost * underlying.shares
    management_income = underlying.lifetime_option_income + underlying.lifetime_dividends
    recovery = calculate_capital_recovery(original, management_income)
    return BasisLensSummary(
        symbol=underlying.symbol,
        original_cost_basis=original,
        lifetime_option_income=underlying.lifetime_option_income,
        lifetime_dividends=underlying.lifetime_dividends,
        lifetime_management_income=management_income,
        income_adjusted_basis=recovery.income_adjusted_basis,
        income_adjusted_basis_per_share=underlying.income_adjusted_basis_per_share,
        basis_offset_percent=recovery.recovered_percent,
        capital_remaining=recovery.capital_remaining,
        recovery_surplus=recovery.recovery_surplus,
        fully_recovered=recovery.fully_recovered,
    )
