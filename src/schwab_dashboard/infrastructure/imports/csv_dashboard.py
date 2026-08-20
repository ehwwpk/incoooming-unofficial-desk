from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from schwab_dashboard.application.alerts import build_desk_alerts
from schwab_dashboard.application.dashboard.calculations import (
    summarize_allocations,
    summarize_portfolio,
    summarize_risk,
)
from schwab_dashboard.application.dashboard.expiration_calendar import (
    build_expiration_calendar,
)
from schwab_dashboard.application.dashboard.live_call_history import project_call_sale_records
from schwab_dashboard.application.dashboard.live_campaigns import project_campaign_summaries
from schwab_dashboard.application.dashboard.live_performance import build_live_performance
from schwab_dashboard.application.dashboard.live_positions import build_live_position_book
from schwab_dashboard.application.dashboard.live_underlying_stats import (
    build_live_underlying_stats,
)
from schwab_dashboard.application.dashboard.models import (
    DashboardSnapshot,
    IncomeSummary,
    PositionSummary,
    RiskSummary,
)
from schwab_dashboard.application.dashboard.option_activity import (
    build_option_outcomes,
    build_recent_option_activity,
)
from schwab_dashboard.application.dashboard.premium_pace import build_open_premium_pace
from schwab_dashboard.application.ports.source_store import SourceDatasetStore

ZERO = Decimal("0")


class CsvDashboardReader:
    def __init__(self, *, store: SourceDatasetStore, dataset_id: str) -> None:
        self._store = store
        self._dataset_id = dataset_id

    def execute(self) -> DashboardSnapshot:
        dataset = self._store.get_dataset(self._dataset_id)
        if dataset is None:
            raise LookupError("The selected CSV dataset no longer exists.")
        records = self._store.load_records(dataset.id)
        positions = tuple(
            _position(item["normalized"]) for item in records if item["kind"] == "position"
        )
        executions = tuple(
            _analytics_record(item["normalized"]) for item in records if item["kind"] == "execution"
        )
        cash_movements = tuple(
            _analytics_record(item["normalized"])
            for item in records
            if item["kind"] == "cash_movement"
        )
        lifecycle_events = tuple(
            _analytics_record(item["normalized"]) for item in records if item["kind"] == "lifecycle"
        )
        as_of = dataset.created_at
        portfolio = summarize_portfolio(positions)
        live_book = build_live_position_book(
            positions,
            as_of=as_of.date(),
            executions=executions,
        )
        open_premium_pace = build_open_premium_pace(live_book, executions)
        covered_capital = sum(
            (abs(item.market_value or ZERO) for item in live_book.underlyings), ZERO
        )
        performance = build_live_performance(
            executions=executions,
            cash_movements=cash_movements,
            lifecycle_events=lifecycle_events,
            live_book=live_book,
            covered_capital=covered_capital,
            as_of=as_of.date(),
        )
        underlyings = build_live_underlying_stats(
            live_book=live_book,
            positions=positions,
            executions=executions,
            cash_movements=cash_movements,
            lifecycle_events=lifecycle_events,
            daily_bars=(),
            option_market=(),
            as_of=as_of.date(),
        )
        campaigns = project_campaign_summaries(
            executions,
            lifecycle_events,
            live_book=live_book,
            as_of=as_of.date(),
        )
        has_activity = bool(executions or cash_movements or lifecycle_events)
        base_risk = summarize_risk(positions)
        risk = RiskSummary(
            buying_power_used_percent=ZERO,
            portfolio_delta=None,
            daily_theta=ZERO,
            short_contracts=live_book.open_call_contracts + live_book.open_put_contracts,
            next_expiration=min(
                (item.expires_on for item in (*live_book.calls, *live_book.puts)),
                default=None,
            ),
            largest_position_percent=base_risk.largest_position_percent,
            open_campaigns=sum(item.status == "OPEN" for item in campaigns),
        )
        account_masks = tuple(sorted({item.account_mask for item in positions})) or ("...CSV",)
        return DashboardSnapshot(
            mode="csv",
            as_of=as_of,
            credentials_configured=False,
            token_available=False,
            latest_sync=None,
            latest_sync_attempt=None,
            accounts=tuple(
                {
                    "id": f"csv:{dataset.id}:{mask}",
                    "account_mask": mask,
                    "account_type": f"{dataset.broker.value.upper()} CSV",
                }
                for mask in account_masks
            ),
            portfolio=portfolio,
            income=(
                performance.income
                if has_activity
                else IncomeSummary(
                    week=ZERO,
                    month=ZERO,
                    quarter=ZERO,
                    year_to_date=ZERO,
                    win_rate=ZERO,
                    annualized_yield=ZERO,
                )
            ),
            income_periods=performance.income_periods if has_activity else (),
            cash_events=performance.cash_events,
            cash_activity_windows=(performance.cash_activity_windows if has_activity else ()),
            cash_chart_series=performance.cash_chart_series if has_activity else (),
            campaigns=campaigns,
            covered_calls=performance.covered_calls,
            underlyings=underlyings,
            alerts=build_desk_alerts(
                underlyings,
                as_of=as_of.date(),
                put_positions=live_book.puts,
            ),
            call_history=project_call_sale_records(
                executions,
                lifecycle_events,
                daily_bars=(),
                as_of=as_of.date(),
            ),
            performance_windows=performance.performance_windows if has_activity else (),
            monthly_performance=performance.monthly_performance if has_activity else (),
            strategy_attribution=(),
            expiration_calendar=build_expiration_calendar(
                underlyings, as_of.date(), put_positions=live_book.puts
            ),
            policies=(),
            quarter_history=(),
            operator_metrics=performance.operator_metrics,
            basis_lens=(),
            positions=positions,
            allocations=summarize_allocations(positions),
            risk=risk,
            live_position_book=live_book,
            recent_option_activity=build_recent_option_activity(
                executions,
                as_of=as_of.date(),
            ),
            option_outcomes=build_option_outcomes(
                executions,
                lifecycle_events,
                as_of=as_of.date(),
                open_call_contracts=live_book.open_call_contracts,
                open_put_contracts=live_book.open_put_contracts,
            ),
            open_premium_pace=open_premium_pace,
        )


def _position(value: object) -> PositionSummary:
    if not isinstance(value, dict):
        raise ValueError("stored CSV position is not an object")
    return PositionSummary(
        account_mask=str(value["account_mask"]),
        symbol=str(value["symbol"]),
        description=str(value["description"]),
        asset_type=str(value["asset_type"]),
        quantity=_decimal(value["quantity"]),
        average_price=_optional_decimal(value.get("average_price")),
        mark=_optional_decimal(value.get("mark")),
        market_value=_optional_decimal(value.get("market_value")),
        day_profit_loss=_optional_decimal(value.get("day_profit_loss")),
        day_profit_loss_percent=_optional_decimal(value.get("day_profit_loss_percent")),
        strategy=str(value["strategy"]) if value.get("strategy") else None,
        underlying_symbol=(
            str(value["underlying_symbol"]) if value.get("underlying_symbol") else None
        ),
        option_type=str(value["option_type"]) if value.get("option_type") else None,
        expiration_date=_optional_date(value.get("expiration_date")),
        strike=_optional_decimal(value.get("strike")),
        open_profit_loss=_optional_decimal(value.get("open_profit_loss")),
        contract_multiplier=_optional_decimal(value.get("contract_multiplier")),
        multiplier_source=(
            str(value["multiplier_source"]) if value.get("multiplier_source") else None
        ),
    )


def _analytics_record(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("stored CSV activity is not an object")
    result: dict[str, Any] = dict(value)
    if result.get("asset_type"):
        result["asset_type"] = str(result["asset_type"]).lower()
    if result.get("option_type"):
        result["option_side"] = str(result["option_type"]).lower()
    if result.get("occurred_at"):
        result["occurred_at"] = datetime.fromisoformat(str(result["occurred_at"]))
    if result.get("expiration_date"):
        result["expiration_date"] = date.fromisoformat(str(result["expiration_date"]))
    for key in (
        "quantity",
        "price",
        "gross_amount",
        "fees",
        "net_cash",
        "amount",
        "option_quantity",
        "stock_quantity",
        "cash_amount",
        "strike",
        "contract_multiplier",
    ):
        if result.get(key) is not None:
            result[key] = _decimal(result[key])
    return result


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None else _decimal(value)


def _optional_date(value: object) -> date | None:
    return date.fromisoformat(str(value)) if value else None
