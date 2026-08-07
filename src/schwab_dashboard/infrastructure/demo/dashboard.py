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
from schwab_dashboard.infrastructure.demo.fixtures.positions import (
    build_allocations,
    build_positions,
)

D = Decimal


class DemoDashboardReader:
    """Return stable fictional data without touching the real brokerage ledger."""

    def execute(self) -> DashboardSnapshot:
        call_history = build_call_history()
        underlyings = build_underlying_stats(call_history)
        covered_calls = build_covered_call_summary(call_history, underlyings)
        return DashboardSnapshot(
            mode="demo",
            as_of=datetime(2026, 8, 7, 21, 15, tzinfo=UTC),
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
                total_value=D("230006.00"),
                invested_value=D("211256.00"),
                cash_value=D("18750.00"),
                stock_value=D("214019.00"),
                option_value=D("-2763.00"),
                day_profit_loss=D("1687.00"),
                day_profit_loss_percent=D("0.7389"),
            ),
            income=IncomeSummary(
                week=D("-105.00"),
                month=D("1015.00"),
                quarter=covered_calls.net_option_cash,
                year_to_date=covered_calls.total_cash_income,
                win_rate=covered_calls.win_rate,
                annualized_yield=covered_calls.annualized_option_yield,
                monthly_target=D("3000.00"),
                target_progress_percent=D("33.8"),
            ),
            income_periods=build_income_periods(),
            campaigns=build_campaigns(),
            covered_calls=covered_calls,
            underlyings=underlyings,
            call_history=call_history,
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
