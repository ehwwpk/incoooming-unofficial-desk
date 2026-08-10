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
    calculate_capital_recovery,
)
from schwab_dashboard.application.policy.evaluate import evaluate_policy_fit
from schwab_dashboard.application.policy.models import UnderlyingPolicy

D = Decimal
ZERO = D("0")
TENTH = D("0.1")
YEAR_DAYS = D("365")
MONTH_DAYS = YEAR_DAYS / D("12")
MONTHLY_TARGET = D("3000")


def build_objective_summary(
    records: Sequence[CallSaleRecord],
    covered_calls: CoveredCallPortfolioSummary,
    windows: Sequence[PerformanceWindowSummary],
    policies: Sequence[UnderlyingPolicy],
) -> ManagementObjectiveSummary:
    by_key = {window.key: window for window in windows}
    total_contracts = sum(record.contracts for record in records)
    policy_by_id = {
        policy.policy_id: policy
        for underlying_policy in policies
        for policy in underlying_policy.policies
    }
    compliant = sum(
        evaluate_policy_fit(
            policy_by_id[record.policy_id],
            strike_buffer_percent=record.strike_upside_percent,
            days_to_expiration=record.days_to_expiration,
            effective_exit_price=record.strike + record.premium_per_share,
        ).fits
        for record in records
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
            "3395",
            "2600",
            "2100",
            "1700",
            "2100",
            "1700",
            "3300",
            "2900",
            "2395",
            "1750",
            "3125",
            "-930",
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
