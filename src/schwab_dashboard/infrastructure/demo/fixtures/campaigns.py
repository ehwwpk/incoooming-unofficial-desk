from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from schwab_dashboard.application.dashboard.covered_calls import (
    CallSaleRecord,
    OpenCallClock,
    UnderlyingCallStats,
)
from schwab_dashboard.application.dashboard.models import CampaignSummary
from schwab_dashboard.application.policy.models import CallPolicy, UnderlyingPolicy
from schwab_dashboard.application.values import sum_if_complete

D = Decimal
ZERO = D("0")
TENTH = D("0.1")


def build_campaigns(
    records: Sequence[CallSaleRecord],
    underlyings: Sequence[UnderlyingCallStats],
    policies: Sequence[UnderlyingPolicy],
    as_of: date,
) -> tuple[CampaignSummary, ...]:
    """Project lifecycle records into roll-aware campaign economics."""

    by_campaign: dict[str, list[CallSaleRecord]] = defaultdict(list)
    for record in records:
        by_campaign[record.campaign_id].append(record)

    name_by_symbol = {item.symbol: item for item in underlyings}
    clock_by_record = {
        clock.record_id: clock
        for underlying in underlyings
        for clock in underlying.open_call_clocks
    }
    policy_by_id = {
        policy.policy_id: policy
        for underlying_policy in policies
        for policy in underlying_policy.policies
    }

    campaigns = tuple(
        _campaign(
            campaign_id,
            campaign_records,
            name_by_symbol,
            clock_by_record,
            policy_by_id,
            as_of,
        )
        for campaign_id, campaign_records in by_campaign.items()
    )
    return tuple(
        sorted(
            campaigns,
            key=lambda item: (item.status != "OPEN", item.expires_on, item.symbol),
        )
    )


def _campaign(
    campaign_id: str,
    records: Sequence[CallSaleRecord],
    name_by_symbol: dict[str, UnderlyingCallStats],
    clock_by_record: dict[str, OpenCallClock],
    policy_by_id: dict[str, CallPolicy],
    as_of: date,
) -> CampaignSummary:
    ordered = sorted(records, key=lambda item: (item.sold_on, item.expires_on))
    first = ordered[0]
    current = ordered[-1]
    underlying = name_by_symbol[first.symbol]
    open_records = [record for record in ordered if record.outcome == "Open"]
    completed_records = [record for record in ordered if record.outcome != "Open"]
    clocks = [clock_by_record[record.record_id] for record in open_records]
    policy = policy_by_id[current.policy_id]
    gross_credit = sum((record.gross_premium for record in ordered), ZERO)
    closing_debits = sum((record.buyback_cost for record in ordered), ZERO)
    fees = sum((record.fees for record in ordered), ZERO)
    realized_cash = sum((record.net_cash - record.fees for record in completed_records), ZERO)
    open_credit = sum((record.gross_premium for record in open_records), ZERO)
    estimated_close = sum_if_complete(clock.current_option_value for clock in clocks)
    assert estimated_close is not None
    collateral = (
        D(max(record.contracts for record in ordered)) * D("100") * underlying.current_price
    )
    progress = _weighted_progress(clocks)
    assigned = sum(record.contracts * 100 for record in ordered if record.outcome == "Assigned")
    assigned_records = [record for record in ordered if record.outcome == "Assigned"]
    effective_exit = (
        assigned_records[-1].strike + assigned_records[-1].premium_per_share
        if assigned_records
        else None
    )
    status = "OPEN" if open_records else current.outcome.upper()
    expires_on = max(record.expires_on for record in ordered)
    net_cash = gross_credit - closing_debits - fees
    return CampaignSummary(
        campaign_id=campaign_id,
        symbol=first.symbol,
        intent_label=policy.intent.label,
        status=status,
        opened_on=first.sold_on,
        expires_on=expires_on,
        days_to_expiration=max(0, (expires_on - as_of).days),
        legs=tuple(_leg_label(record) for record in ordered),
        gross_opening_credit=gross_credit,
        closing_debits=closing_debits,
        fees=fees,
        net_cash_to_date=net_cash,
        realized_cash=realized_cash,
        open_credit=open_credit,
        estimated_close_value=estimated_close,
        open_mark_profit_loss=open_credit - estimated_close,
        initial_strike=first.strike,
        current_strike=current.strike,
        strike_change=current.strike - first.strike,
        days_extended=max(0, (current.expires_on - first.expires_on).days),
        called_away_shares=D(assigned),
        effective_exit_price=effective_exit,
        collateral=collateral,
        cash_on_capital_percent=(net_cash / collateral * 100).quantize(TENTH)
        if collateral
        else ZERO,
        progress_percent=progress,
    )


def _weighted_progress(clocks: Sequence[OpenCallClock]) -> int:
    contracts = sum(clock.contracts for clock in clocks)
    if not contracts:
        return 100
    weighted = sum_if_complete(
        (
            clock.elapsed_time_percent * clock.contracts
            if clock.elapsed_time_percent is not None
            else None
        )
        for clock in clocks
    )
    assert weighted is not None
    value = weighted / contracts
    return max(0, min(100, int(value)))


def _leg_label(record: CallSaleRecord) -> str:
    action = "OPEN" if record.outcome == "Open" else record.outcome.upper()
    return (
        f"{record.sold_on:%b %d} · {record.contracts}x ${record.strike:g}C · "
        f"{record.expires_on:%b %d} · {action}"
    )
