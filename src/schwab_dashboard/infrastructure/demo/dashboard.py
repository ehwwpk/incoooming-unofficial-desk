from datetime import UTC, date, datetime
from decimal import Decimal

from schwab_dashboard.application.alerts import build_desk_alerts
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
from schwab_dashboard.infrastructure.demo.fixtures.obligations import (
    build_expiration_calendar,
)
from schwab_dashboard.infrastructure.demo.fixtures.performance import (
    build_basis_lens,
    build_cash_chart_series,
    build_monthly_performance,
    build_operator_metrics,
    build_performance_windows,
    build_quarter_history,
    build_strategy_attribution,
)
from schwab_dashboard.infrastructure.demo.fixtures.policies import build_policies
from schwab_dashboard.infrastructure.demo.fixtures.positions import (
    build_allocations,
    build_positions,
)

D = Decimal


class DemoDashboardReader:
    """Return stable fictional data without touching the real brokerage ledger."""

    def execute(self) -> DashboardSnapshot:
        call_history = build_call_history()
        as_of = date(2026, 8, 7)
        underlyings = build_underlying_stats(call_history, as_of)
        covered_calls = build_covered_call_summary(call_history, underlyings)
        positions = build_positions()
        cash_value = D("18750.00")
        stock_value = sum(
            (
                (position.market_value or D("0"))
                for position in positions
                if position.asset_type == "EQUITY"
            ),
            D("0"),
        )
        option_value = sum(
            (
                (position.market_value or D("0"))
                for position in positions
                if position.asset_type == "OPTION"
            ),
            D("0"),
        )
        day_profit_loss = sum(
            ((position.day_profit_loss or D("0")) for position in positions), D("0")
        )
        total_value = stock_value + option_value + cash_value
        previous_value = total_value - day_profit_loss
        monthly_performance = build_monthly_performance()
        performance_windows = build_performance_windows(
            call_history, stock_value, as_of, monthly_performance
        )
        policies = build_policies()
        campaigns = build_campaigns(call_history, underlyings, policies, as_of)
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
                total_value=total_value,
                invested_value=stock_value + option_value,
                cash_value=cash_value,
                stock_value=stock_value,
                option_value=option_value,
                day_profit_loss=day_profit_loss,
                day_profit_loss_percent=(day_profit_loss / previous_value * 100).quantize(
                    D("0.0001")
                ),
            ),
            income=IncomeSummary(
                week=D("80.00"),
                month=windows_by_key["month"].option_cash,
                quarter=covered_calls.net_option_cash,
                year_to_date=windows_by_key["ytd"].total_cash,
                win_rate=covered_calls.win_rate,
                annualized_yield=covered_calls.annualized_option_yield,
            ),
            income_periods=build_income_periods(call_history),
            cash_chart_series=build_cash_chart_series(call_history, monthly_performance, as_of),
            campaigns=campaigns,
            covered_calls=covered_calls,
            underlyings=underlyings,
            alerts=build_desk_alerts(underlyings, as_of=as_of),
            call_history=call_history,
            performance_windows=performance_windows,
            monthly_performance=monthly_performance,
            strategy_attribution=build_strategy_attribution(
                call_history, underlyings, performance_windows, as_of
            ),
            expiration_calendar=build_expiration_calendar(underlyings, as_of),
            policies=policies,
            quarter_history=build_quarter_history(),
            operator_metrics=build_operator_metrics(
                call_history,
                covered_calls,
                performance_windows,
                policies,
                monthly_performance,
            ),
            basis_lens=build_basis_lens(underlyings),
            positions=positions,
            allocations=build_allocations(positions, cash_value),
            risk=RiskSummary(
                buying_power_used_percent=D("7.8"),
                portfolio_delta=D("1624.0"),
                daily_theta=sum(
                    (item.open_call_theta_per_day for item in underlyings),
                    D("0"),
                ),
                short_contracts=covered_calls.active_contracts,
                next_expiration=min(
                    clock.expires_on for item in underlyings for clock in item.open_call_clocks
                ),
                largest_position_percent=D("58.8"),
                open_campaigns=sum(campaign.status == "OPEN" for campaign in campaigns),
            ),
        )
