from datetime import UTC, date, datetime
from decimal import Decimal

from schwab_dashboard.application.dashboard.models import (
    DashboardSnapshot,
    IncomeSummary,
    PortfolioSummary,
    RiskSummary,
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
                total_value=D("407733.00"),
                invested_value=D("333173.00"),
                cash_value=D("74560.00"),
                stock_value=D("334245.00"),
                option_value=D("-1072.00"),
                day_profit_loss=D("1722.00"),
                day_profit_loss_percent=D("0.4244"),
            ),
            income=IncomeSummary(
                week=D("1248.50"),
                month=D("1248.50"),
                quarter=D("12774.10"),
                year_to_date=D("31845.75"),
                win_rate=D("78.4"),
                annualized_yield=D("11.7"),
                monthly_target=D("6000.00"),
                target_progress_percent=D("20.8"),
            ),
            income_periods=build_income_periods(),
            campaigns=build_campaigns(),
            positions=build_positions(),
            allocations=build_allocations(),
            risk=RiskSummary(
                buying_power_used_percent=D("31.8"),
                portfolio_delta=D("126.4"),
                daily_theta=D("84.25"),
                short_contracts=9,
                next_expiration=date(2026, 8, 14),
                largest_position_percent=D("36.8"),
                open_campaigns=3,
            ),
        )
