from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from schwab_dashboard.domain.instruments import OptionSide


class CampaignLinkConfidence(StrEnum):
    EXACT = "exact"
    USER_CONFIRMED = "user_confirmed"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class CampaignAnnotation:
    record_key: str
    campaign_id: str
    campaign_label: str
    confidence: CampaignLinkConfidence
    leg_index: int
    net_cash_to_date: Decimal


@dataclass(frozen=True, slots=True)
class OptionCampaign:
    campaign_id: str
    campaign_label: str
    symbol: str
    option_side: OptionSide
    opened_on: date
    closed_on: date | None
    status: str
    event_keys: tuple[str, ...]
    net_cash_to_date: Decimal
    confidence: CampaignLinkConfidence


@dataclass(frozen=True, slots=True)
class CampaignLedger:
    campaigns: tuple[OptionCampaign, ...]
    annotations: tuple[CampaignAnnotation, ...]

    def annotation_for(self, record_key: str) -> CampaignAnnotation | None:
        return next(
            (item for item in self.annotations if item.record_key == record_key),
            None,
        )
