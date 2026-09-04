from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ChartBar:
    time: date | datetime
    value: Decimal
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal | None = None
    volume: int | None = None


@dataclass(frozen=True, slots=True)
class ChartInterval:
    key: str
    label: str
    minutes: int
    bars: tuple[ChartBar, ...]
    extended_hours: bool


@dataclass(frozen=True, slots=True)
class ChartLeg:
    id: str
    sequence: int
    campaign_id: str
    campaign_label: str
    leg_index: int
    time: date | datetime
    time_precision: str
    underlying_price: Decimal
    event_type: str
    outcome: str
    option_side: str
    strike: Decimal
    expiration: date
    contracts: int
    net_cash: Decimal
    campaign_net_cash: Decimal
    detail: str
    confidence: str
    is_open: bool
    contract_multiplier: Decimal = Decimal("100")
    delivered_shares: Decimal | None = None


@dataclass(frozen=True, slots=True)
class ChartCampaign:
    id: str
    label: str
    option_side: str
    status: str
    confidence: str
    opened_on: date
    latest_on: date
    net_cash: Decimal
    legs: tuple[ChartLeg, ...]
    risk_reference: ChartRiskReference | None = None
    settlement: ChartSettlementState | None = None


@dataclass(frozen=True, slots=True)
class ChartSettlementState:
    """Provisional post-trading state for a broker-reported open campaign."""

    session_state: str
    session_label: str
    expectation: str
    expectation_label: str
    reference_price: Decimal | None
    reference_label: str
    can_close_or_roll: bool


@dataclass(frozen=True, slots=True)
class ChartRiskReference:
    spot: Decimal
    strike: Decimal
    expiration: date
    days_to_expiration: int
    implied_volatility_percent: Decimal | None
    expected_move: Decimal | None
    expected_move_low: Decimal | None
    expected_move_high: Decimal | None
    quote_observed_on: date | None
    source: str


@dataclass(frozen=True, slots=True)
class ChartShareEvent:
    time: date
    action: str
    shares: Decimal
    price: Decimal
    detail: str


@dataclass(frozen=True, slots=True)
class ChartAudit:
    campaigns: int
    events: int
    exact_campaigns: int
    inferred_campaigns: int
    unknown_campaigns: int
    needs_review_campaigns: int
    removal_gate_passed: bool


@dataclass(frozen=True, slots=True)
class CampaignChart:
    version: str
    symbol: str
    as_of: date
    bars: tuple[ChartBar, ...]
    intervals: tuple[ChartInterval, ...]
    default_interval: str
    campaigns: tuple[ChartCampaign, ...]
    share_events: tuple[ChartShareEvent, ...]
    audit: ChartAudit
