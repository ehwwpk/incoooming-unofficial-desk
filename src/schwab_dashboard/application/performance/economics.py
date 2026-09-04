from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

from schwab_dashboard.application.campaigns import reconcile_option_campaigns
from schwab_dashboard.application.campaigns.audit import audit_campaign_ledger
from schwab_dashboard.application.campaigns.models import CampaignLinkConfidence
from schwab_dashboard.application.dashboard.short_premium import (
    is_closing_buy,
    is_opening_sale,
    is_short_premium_execution,
)
from schwab_dashboard.application.market_time import ledger_market_date
from schwab_dashboard.application.performance.models import OptionEconomics

ZERO = Decimal("0")


def calculate_option_economics(
    *,
    executions: Sequence[dict[str, Any]],
    lifecycle_events: Sequence[dict[str, Any]],
    position_history: Sequence[dict[str, Any]],
    coverage_start: date | None,
    coverage_end: date | None,
) -> OptionEconomics:
    in_window = tuple(
        row
        for row in executions
        if is_short_premium_execution(row)
        and _inside(_date(row.get("occurred_at")), coverage_start, coverage_end)
    )
    opening_credits = sum((_gross(row) for row in in_window if is_opening_sale(row)), ZERO)
    closing_debits = sum((_gross(row) for row in in_window if is_closing_buy(row)), ZERO)
    fees = sum((_decimal(row.get("fees")) for row in in_window), ZERO)
    net_cash = sum((_decimal(row.get("net_cash")) for row in in_window), ZERO)

    ledger = reconcile_option_campaigns(executions, lifecycle_events)
    audit = audit_campaign_ledger(ledger, executions, lifecycle_events)
    closed = tuple(
        campaign
        for campaign in ledger.campaigns
        if campaign.status != "OPEN" and _inside(campaign.closed_on, coverage_start, coverage_end)
    )
    exact = sum(
        campaign.confidence in {CampaignLinkConfidence.EXACT, CampaignLinkConfidence.USER_CONFIRMED}
        for campaign in closed
    )
    inferred = sum(campaign.confidence is CampaignLinkConfidence.INFERRED for campaign in closed)
    latest_positions = _latest_position_rows(position_history)
    short_options = tuple(
        row
        for row in latest_positions
        if str(row.get("asset_type") or "").upper() == "OPTION"
        and _decimal(row.get("net_quantity")) < ZERO
    )
    open_mark_values = [
        _decimal(row.get("short_open_profit_loss"))
        for row in short_options
        if row.get("short_open_profit_loss") is not None
    ]
    liabilities = [
        abs(_decimal(row.get("market_value")))
        for row in short_options
        if row.get("market_value") is not None
    ]
    status = (
        "reconciled"
        if audit.cash_variance == ZERO and audit.unknown_campaigns == 0
        else "review_needed"
    )
    completed_result = (
        sum((item.net_cash_to_date for item in closed), ZERO)
        if audit.cash_variance == ZERO and audit.unknown_campaigns == 0
        else None
    )
    return OptionEconomics(
        status=status,
        opening_credits=opening_credits,
        closing_debits=closing_debits,
        fees=fees,
        net_executed_cash=net_cash,
        closed_campaign_result=completed_result,
        closed_campaigns=len(closed),
        exact_closed_campaigns=exact,
        inferred_closed_campaigns=inferred,
        open_mark_profit_loss=(
            sum(open_mark_values, ZERO)
            if short_options and len(open_mark_values) == len(short_options)
            else None
        ),
        current_option_liability=(
            sum(liabilities, ZERO)
            if short_options and len(liabilities) == len(short_options)
            else None
        ),
        campaign_cash_variance=audit.cash_variance,
        slippage_status="not_measured",
        method_note=(
            "Window cash is fee-net broker cash. Closed-campaign P/L includes campaigns that "
            "finished inside the same return window and is withheld when campaign links do not "
            "reconcile. Open mark P/L remains unrealized and is shown only when every current "
            "short option has a broker value. Slippage needs execution-time bid/ask snapshots "
            "and is not estimated."
        ),
    )


def _latest_position_rows(rows: Sequence[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    latest: dict[str, dict[str, Any]] = {}
    for row in rows:
        account = _account_key(row)
        observed = row.get("observed_at")
        previous = latest.get(account)
        if (
            previous is None
            or previous.get("observed_at") is None
            or (observed is not None and _timestamp(observed) > _timestamp(previous["observed_at"]))
        ):
            latest[account] = row
    latest_keys = {(_account_key(row), row.get("observed_at")) for row in latest.values()}
    return tuple(row for row in rows if (_account_key(row), row.get("observed_at")) in latest_keys)


def _account_key(row: dict[str, Any]) -> str:
    return str(row.get("account_id") or row.get("account_mask") or "ACCOUNT")


def _timestamp(value: object) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=UTC)
    return datetime.min.replace(tzinfo=UTC)


def _gross(row: dict[str, Any]) -> Decimal:
    return abs(_decimal(row.get("gross_amount")))


def _inside(value: date | None, start: date | None, end: date | None) -> bool:
    return value is not None and (start is None or value >= start) and (end is None or value <= end)


def _date(value: object) -> date | None:
    if isinstance(value, (date, datetime)):
        return ledger_market_date(value)
    return date.fromisoformat(str(value)) if value else None


def _decimal(value: object) -> Decimal:
    return ZERO if value is None else Decimal(str(value))
