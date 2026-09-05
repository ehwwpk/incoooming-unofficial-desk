from datetime import UTC, date, datetime
from decimal import Decimal

from schwab_dashboard.application.alerts import build_desk_alerts
from schwab_dashboard.application.dashboard.calculations import (
    account_day_profit_loss,
    broker_day_profit_loss,
)
from schwab_dashboard.application.dashboard.cash_activity import (
    build_cash_activity_items,
    build_cash_activity_windows,
)
from schwab_dashboard.application.dashboard.cashflows import build_call_cash_events
from schwab_dashboard.application.dashboard.expiration_calendar import (
    build_expiration_calendar,
)
from schwab_dashboard.application.dashboard.live_campaigns import project_campaign_summaries
from schwab_dashboard.application.dashboard.models import (
    DashboardSnapshot,
    IncomeSummary,
    PortfolioSummary,
    RiskSummary,
)
from schwab_dashboard.application.dashboard.option_activity import (
    OptionOutcomeSummary,
    RecentOptionActivityItem,
)
from schwab_dashboard.application.dashboard.premium_pace import build_open_premium_pace
from schwab_dashboard.application.values import sum_if_complete
from schwab_dashboard.infrastructure.demo.fixtures.benchmark_history import (
    build_demo_performance_comparison,
)
from schwab_dashboard.infrastructure.demo.fixtures.call_history import build_call_history
from schwab_dashboard.infrastructure.demo.fixtures.call_stats import (
    build_covered_call_summary,
    build_underlying_stats,
)
from schwab_dashboard.infrastructure.demo.fixtures.campaigns import build_campaigns
from schwab_dashboard.infrastructure.demo.fixtures.cash_events import build_dividend_cash_events
from schwab_dashboard.infrastructure.demo.fixtures.income import build_income_periods
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
from schwab_dashboard.infrastructure.demo.fixtures.position_book import (
    build_demo_opening_executions,
    build_demo_position_book,
)
from schwab_dashboard.infrastructure.demo.fixtures.positions import (
    build_allocations,
    build_positions,
)
from schwab_dashboard.infrastructure.demo.fixtures.short_puts import (
    build_put_cash_activity_items,
    build_put_executions,
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
        position_book = build_demo_position_book(positions, call_history, as_of=as_of)
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
        total_value = stock_value + option_value + cash_value
        open_day_profit_loss, open_day_profit_loss_percent = broker_day_profit_loss(
            positions,
            current_account_value=total_value,
        )
        comparison = build_demo_performance_comparison(
            positions=positions,
            cash_value=cash_value,
            call_history=call_history,
            as_of=as_of,
            put_executions=build_put_executions(),
        )
        account_day = account_day_profit_loss(comparison.actual.points)
        monthly_performance = build_monthly_performance()
        performance_windows = build_performance_windows(
            call_history, stock_value, as_of, monthly_performance
        )
        cash_events = tuple(
            sorted(
                (
                    *build_cash_activity_items(
                        call_history,
                        build_call_cash_events(call_history),
                        build_dividend_cash_events(),
                    ),
                    *build_put_cash_activity_items(),
                ),
                key=lambda event: (event.occurred_on, event.event_id),
                reverse=True,
            )
        )
        cash_activity_windows = build_cash_activity_windows(
            cash_events,
            performance_windows,
            as_of,
        )
        recent_option_activity = tuple(
            RecentOptionActivityItem(
                event_id=event.event_id,
                occurred_at=datetime(
                    event.occurred_on.year,
                    event.occurred_on.month,
                    event.occurred_on.day,
                    16,
                    tzinfo=UTC,
                ),
                occurred_on=event.occurred_on,
                date_label=(
                    "TODAY"
                    if event.occurred_on == as_of
                    else event.occurred_on.strftime("%b %d").upper()
                ),
                symbol=event.symbol,
                action_label=event.action_label,
                detail=f"{event.contracts} {'CONTRACT' if event.contracts == 1 else 'CONTRACTS'}",
                amount=event.amount,
                contracts=event.contracts,
                tone="roll" if "ROLLED" in event.action_label else event.tone,
                anchor_id=event.anchor_id,
                leg_count=2 if "ROLLED" in event.action_label else 1,
            )
            for event in cash_events
            if event.contracts
        )[:8]
        policies = build_policies()
        campaigns = build_campaigns(call_history, underlyings, policies, as_of)
        campaigns += project_campaign_summaries(
            build_put_executions(), (), live_book=position_book, as_of=as_of
        )
        windows_by_key = {window.key: window for window in performance_windows}
        daily_theta = sum_if_complete(
            item.estimated_option_theta_per_day for item in position_book.underlyings
        )
        assert daily_theta is not None
        option_delta = sum_if_complete(
            option.position_delta_share_equivalent
            for option in (*position_book.calls, *position_book.puts)
        )
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
                day_profit_loss=account_day.profit_loss,
                day_profit_loss_percent=account_day.profit_loss_percent,
                day_external_cash_flow=account_day.external_cash_flow,
                day_profit_loss_source=account_day.status,
                day_profit_loss_as_of=account_day.as_of,
                day_profit_loss_previous_as_of=account_day.previous_as_of,
                open_position_day_profit_loss=open_day_profit_loss,
                open_position_day_profit_loss_percent=open_day_profit_loss_percent,
                liquidation_value=total_value,
                maintenance_requirement=comparison.spine.capital_efficiency.maintenance_requirement,
                available_funds=comparison.spine.capital_efficiency.available_funds,
                buying_power=comparison.spine.capital_efficiency.buying_power,
            ),
            income=IncomeSummary(
                week=sum(
                    (event.amount for event in cash_events if (as_of - event.occurred_on).days < 7),
                    D("0"),
                ),
                month=windows_by_key["month"].option_cash,
                quarter=windows_by_key["quarter"].option_cash,
                year_to_date=windows_by_key["ytd"].total_cash,
                win_rate=covered_calls.win_rate,
                annualized_yield=covered_calls.annualized_option_yield,
            ),
            income_periods=build_income_periods(call_history),
            cash_events=cash_events,
            cash_activity_windows=cash_activity_windows,
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
            expiration_calendar=build_expiration_calendar(
                underlyings, as_of, put_positions=position_book.puts
            ),
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
                buying_power_used_percent=None,
                portfolio_delta=(
                    position_book.total_shares + option_delta if option_delta is not None else None
                ),
                daily_theta=daily_theta,
                short_contracts=position_book.actionable_contracts,
                next_expiration=min(
                    option.expires_on for option in (*position_book.calls, *position_book.puts)
                ),
                largest_position_percent=(
                    max(
                        position.market_value or D("0")
                        for position in positions
                        if position.asset_type == "EQUITY"
                    )
                    / total_value
                    * 100
                ).quantize(D("0.1")),
                open_campaigns=sum(campaign.status == "OPEN" for campaign in campaigns),
            ),
            recent_option_activity=recent_option_activity,
            option_outcomes=OptionOutcomeSummary(
                recorded_from=min(record.sold_on for record in call_history),
                recorded_through=as_of,
                expired_contracts=covered_calls.expired_contracts,
                bought_back_contracts=covered_calls.closed_contracts,
                rolled_contracts=covered_calls.rolled_contracts,
                roll_orders=sum(record.outcome == "Rolled" for record in call_history),
                assigned_contracts=covered_calls.assigned_contracts,
                assignment_shares=covered_calls.called_away_shares,
                open_call_contracts=covered_calls.active_contracts,
                open_put_contracts=position_book.open_put_contracts,
            ),
            live_position_book=position_book,
            performance_comparison=comparison,
            open_premium_pace=build_open_premium_pace(
                position_book, build_demo_opening_executions(call_history)
            ),
        )
