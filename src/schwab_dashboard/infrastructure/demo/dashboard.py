from datetime import UTC, date, datetime
from decimal import Decimal

from schwab_dashboard.application.dashboard.models import (
    DashboardSnapshot,
    IncomeSummary,
    PortfolioSummary,
    RiskSummary,
)
from schwab_dashboard.infrastructure.demo.fixtures.call_history import build_call_history
from schwab_dashboard.infrastructure.demo.fixtures.call_stats import (
    build_covered_call_summary,
    build_underlying_stats,
)
from schwab_dashboard.infrastructure.demo.fixtures.campaigns import build_campaigns
from schwab_dashboard.infrastructure.demo.fixtures.income import build_income_periods
from schwab_dashboard.infrastructure.demo.fixtures.performance import (
    build_basis_lens,
    build_objective_summary,
    build_performance_windows,
    build_quarter_history,
)
from schwab_dashboard.infrastructure.demo.fixtures.positions import (
    build_allocations,
    build_positions,
)
from schwab_dashboard.infrastructure.demo.fixtures.strategy_intelligence import (
    build_strategy_insights,
)

D = Decimal


class DemoDashboardReader:
    """Return stable fictional data without touching the real brokerage ledger."""

    def execute(self) -> DashboardSnapshot:
        call_history = build_call_history()
        as_of = date(2026, 8, 7)
        underlyings = build_underlying_stats(call_history, as_of)
        covered_calls = build_covered_call_summary(call_history, underlyings)
        performance_windows = build_performance_windows(covered_calls, D("214019.00"))
        windows_by_key = {window.key: window for window in performance_windows}
        return DashboardSnapshot(
            mode="demo",
            as_of=datetime(as_of.year, as_of.month, as_of.day, 21, 15, tzinfo=UTC),
            credentials_configured=False,
            token_available=False,
            latest_sync=None,
            accounts=(
                {
                    "id": "demo-brokerage",
                    "account_mask": "...4831",
                    "account_type": "MARGIN",
                },
            ),
            portfolio=PortfolioSummary(
                total_value=D("229581.00"),
                invested_value=D("211256.00"),
                cash_value=D("18750.00"),
                stock_value=D("214019.00"),
                option_value=D("-3188.00"),
                day_profit_loss=D("1687.00"),
                day_profit_loss_percent=D("0.7389"),
            ),
            income=IncomeSummary(
                week=D("80.00"),
                month=D("1950.00"),
                quarter=covered_calls.net_option_cash,
                year_to_date=windows_by_key["ytd"].total_cash,
                win_rate=covered_calls.win_rate,
                annualized_yield=covered_calls.annualized_option_yield,
                monthly_target=D("3000.00"),
                target_progress_percent=windows_by_key["month"].target_progress_percent,
            ),
            income_periods=build_income_periods(),
            campaigns=build_campaigns(),
            covered_calls=covered_calls,
            underlyings=underlyings,
            strategy_insights=build_strategy_insights(underlyings),
            call_history=call_history,
            performance_windows=performance_windows,
            quarter_history=build_quarter_history(),
            objective=build_objective_summary(call_history, covered_calls, performance_windows),
            basis_lens=build_basis_lens(underlyings),
            positions=build_positions(),
            allocations=build_allocations(),
            risk=RiskSummary(
                buying_power_used_percent=D("7.8"),
                portfolio_delta=D("1624.0"),
                daily_theta=D("83.40"),
                short_contracts=covered_calls.active_contracts,
                next_expiration=date(2026, 9, 4),
                largest_position_percent=D("58.5"),
                open_campaigns=3,
            ),
        )
