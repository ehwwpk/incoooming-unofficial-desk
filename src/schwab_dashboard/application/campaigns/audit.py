from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from schwab_dashboard.application.campaigns.models import CampaignLedger
from schwab_dashboard.application.dashboard.short_premium import is_short_premium_execution

STANDARD_CONTRACT_MULTIPLIER = Decimal("100")


@dataclass(frozen=True, slots=True)
class CampaignAudit:
    campaigns: int
    annotated_events: int
    exact_campaigns: int
    inferred_campaigns: int
    unknown_campaigns: int
    excluded_long_lifecycle_events: int
    adjusted_contract_events: int
    source_net_cash: Decimal
    campaign_net_cash: Decimal
    cash_variance: Decimal

    @property
    def legacy_removal_gate_passed(self) -> bool:
        return (
            self.annotated_events > 0
            and self.unknown_campaigns == 0
            and self.cash_variance == Decimal("0")
        )


def audit_campaign_ledger(
    ledger: CampaignLedger,
    executions: Sequence[Mapping[str, object]],
    lifecycle_events: Sequence[Mapping[str, object]],
) -> CampaignAudit:
    confidence = Counter(campaign.confidence.value for campaign in ledger.campaigns)
    adjusted_events = sum(
        _is_adjusted(row)
        for row in (*executions, *lifecycle_events)
        if str(row.get("asset_type") or "option") == "option"
    )
    source_net_cash = sum(
        (
            Decimal(str(row.get("net_cash") or "0"))
            for row in executions
            if is_short_premium_execution(row)
        ),
        Decimal("0"),
    )
    campaign_net_cash = sum(
        (campaign.net_cash_to_date for campaign in ledger.campaigns),
        Decimal("0"),
    )
    return CampaignAudit(
        campaigns=len(ledger.campaigns),
        annotated_events=len(ledger.annotations),
        exact_campaigns=confidence["exact"],
        inferred_campaigns=confidence["inferred"],
        unknown_campaigns=confidence["unknown"],
        excluded_long_lifecycle_events=len(ledger.exclusions),
        adjusted_contract_events=adjusted_events,
        source_net_cash=source_net_cash,
        campaign_net_cash=campaign_net_cash,
        cash_variance=campaign_net_cash - source_net_cash,
    )


def _is_adjusted(row: Mapping[str, object]) -> bool:
    multiplier = row.get("contract_multiplier")
    deliverable = row.get("deliverable")
    deliverable_kind = (
        str(deliverable.get("kind") or "").lower()
        if isinstance(deliverable, Mapping)
        else ""
    )
    return bool(
        (multiplier is not None and Decimal(str(multiplier)) != STANDARD_CONTRACT_MULTIPLIER)
        or (deliverable and deliverable_kind != "standard")
    )
