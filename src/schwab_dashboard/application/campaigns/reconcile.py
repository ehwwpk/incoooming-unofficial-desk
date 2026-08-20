from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from schwab_dashboard.application.campaigns.models import (
    CampaignAnnotation,
    CampaignExclusion,
    CampaignLedger,
    CampaignLinkConfidence,
    OptionCampaign,
)
from schwab_dashboard.domain.instruments import OptionSide

ZERO = Decimal("0")


@dataclass(slots=True)
class _WorkingCampaign:
    campaign_id: str
    symbol: str
    option_side: OptionSide
    opened_on: date
    closed_on: date | None = None
    status: str = "OPEN"
    event_keys: list[str] = field(default_factory=list)
    net_cash: Decimal = ZERO
    confidence: CampaignLinkConfidence = CampaignLinkConfidence.EXACT


@dataclass(slots=True)
class _ActiveLot:
    campaign_id: str
    contracts: Decimal


def reconcile_option_campaigns(
    executions: Sequence[Mapping[str, object]],
    lifecycle_events: Sequence[Mapping[str, object]],
) -> CampaignLedger:
    """Reconcile option actions into stable campaigns without rewriting source rows.

    Exact broker order identifiers join a close and replacement leg. Exact option
    identity resolves a sale. When more than one open lot could match, the link is
    retained but marked inferred instead of silently presented as certain.
    """

    records, exclusions = _normalized_records(executions, lifecycle_events)
    campaigns: dict[str, _WorkingCampaign] = {}
    active: defaultdict[str, list[_ActiveLot]] = defaultdict(list)
    annotations: dict[str, tuple[str, CampaignLinkConfidence, int, Decimal]] = {}
    closed_by_order: defaultdict[str, list[_ActiveLot]] = defaultdict(list)

    for record in records:
        key = str(record["record_key"])
        position_key = str(record["position_key"])
        order_key = str(record["order_key"])
        action = str(record["action"])
        contracts = _decimal(record["contracts"])
        confidence = CampaignLinkConfidence.EXACT

        if action == "open":
            roll_parent, roll_confidence = _consume_single_campaign(
                closed_by_order[order_key],
                contracts,
            )
            same_contract_parent = _single_active_campaign(active[position_key])
            confidence = (
                roll_confidence
                if roll_parent
                else CampaignLinkConfidence.INFERRED
                if same_contract_parent
                else CampaignLinkConfidence.EXACT
            )
            campaign_id = roll_parent or same_contract_parent or str(record["record_key"])
            if campaign_id not in campaigns:
                campaigns[campaign_id] = _WorkingCampaign(
                    campaign_id=campaign_id,
                    symbol=str(record["underlying_symbol"]),
                    option_side=OptionSide(str(record["option_side"])),
                    opened_on=_date(record["occurred_at"]),
                )
            campaign = campaigns[campaign_id]
            campaign.status = "OPEN"
            campaign.closed_on = None
            campaign.confidence = _weaker(campaign.confidence, confidence)
            active[position_key].append(_ActiveLot(campaign_id, contracts))
        else:
            consumed_campaign_id, confidence = _consume_single_campaign(
                active[position_key],
                contracts,
            )
            if consumed_campaign_id is not None:
                campaign_id = consumed_campaign_id
                campaign = campaigns[campaign_id]
                confidence = _weaker(confidence, campaign.confidence)
                if _campaign_has_open_contracts(active, campaign_id):
                    campaign.status = "OPEN"
                    campaign.closed_on = None
                else:
                    campaign.status = str(record["status"])
                    campaign.closed_on = _date(record["occurred_at"])
                if action == "close" and order_key:
                    closed_by_order[order_key].append(_ActiveLot(campaign_id, contracts))
            else:
                campaign_id = f"unlinked:{record['record_key']}"
                confidence = CampaignLinkConfidence.UNKNOWN
                campaigns[campaign_id] = _WorkingCampaign(
                    campaign_id=campaign_id,
                    symbol=str(record["underlying_symbol"]),
                    option_side=OptionSide(str(record["option_side"])),
                    opened_on=_date(record["occurred_at"]),
                    confidence=confidence,
                )
                campaign = campaigns[campaign_id]
                campaign.status = str(record["status"])
                campaign.closed_on = _date(record["occurred_at"])

        campaign.event_keys.append(key)
        campaign.net_cash += _decimal(record["net_cash"])
        campaign.confidence = _weaker(campaign.confidence, confidence)
        annotations[key] = (
            campaign_id,
            confidence,
            len(campaign.event_keys),
            campaign.net_cash,
        )

    ordered = sorted(
        campaigns.values(),
        key=lambda item: (item.opened_on, item.symbol, item.option_side.value, item.campaign_id),
    )
    counters: defaultdict[tuple[str, OptionSide], int] = defaultdict(int)
    labels: dict[str, str] = {}
    for campaign in ordered:
        counter_key = (campaign.symbol, campaign.option_side)
        counters[counter_key] += 1
        prefix = "C" if campaign.option_side is OptionSide.CALL else "P"
        labels[campaign.campaign_id] = f"{prefix}{counters[counter_key]}"

    final_campaigns = tuple(
        OptionCampaign(
            campaign_id=item.campaign_id,
            campaign_label=labels[item.campaign_id],
            symbol=item.symbol,
            option_side=item.option_side,
            opened_on=item.opened_on,
            closed_on=item.closed_on,
            status=item.status,
            event_keys=tuple(item.event_keys),
            net_cash_to_date=item.net_cash,
            confidence=item.confidence,
        )
        for item in ordered
    )
    final_annotations = tuple(
        CampaignAnnotation(
            record_key=key,
            campaign_id=campaign_id,
            campaign_label=labels[campaign_id],
            confidence=confidence,
            leg_index=leg_index,
            net_cash_to_date=net_cash_to_date,
        )
        for key, (
            campaign_id,
            confidence,
            leg_index,
            net_cash_to_date,
        ) in annotations.items()
    )
    return CampaignLedger(
        campaigns=final_campaigns,
        annotations=final_annotations,
        exclusions=tuple(exclusions),
    )


def _normalized_records(
    executions: Sequence[Mapping[str, object]],
    lifecycle_events: Sequence[Mapping[str, object]],
) -> tuple[list[dict[str, object]], list[CampaignExclusion]]:
    records: list[dict[str, object]] = []
    exclusions: list[CampaignExclusion] = []
    long_inventory = _long_option_inventory(executions)
    for row in executions:
        if str(row.get("asset_type")) != "option":
            continue
        opening = str(row.get("side")) == "sell" and str(row.get("position_effect")) == "opening"
        closing = str(row.get("side")) == "buy" and str(row.get("position_effect")) == "closing"
        if not (opening or closing):
            continue
        records.append(
            {
                "record_key": _record_key(row),
                "order_key": _scoped_key(row, "order_external_key"),
                "position_key": _scoped_key(row, "symbol"),
                "underlying_symbol": str(row.get("underlying_symbol")),
                "option_side": str(row.get("option_side") or "call").lower(),
                "occurred_at": _datetime(row.get("occurred_at")),
                "contracts": abs(_decimal(row.get("quantity"))),
                "action": "open" if opening else "close",
                "status": "CLOSED",
                "net_cash": _decimal(row.get("net_cash")),
                "sort_order": 0 if closing else 1,
            }
        )
    for row in lifecycle_events:
        event_type = str(row.get("event_type"))
        if event_type not in {"expiration", "assignment"}:
            continue
        if _consume_long_inventory(long_inventory, row):
            exclusions.append(
                CampaignExclusion(
                    record_key=_record_key(row),
                    reason="LONG OPTION LIFECYCLE — OUTSIDE SHORT-PREMIUM CAMPAIGNS",
                )
            )
            continue
        records.append(
            {
                "record_key": _record_key(row),
                "order_key": "",
                "position_key": _scoped_key(row, "symbol"),
                "underlying_symbol": str(row.get("underlying_symbol")),
                "option_side": str(row.get("option_side") or "call").lower(),
                "occurred_at": _datetime(row.get("occurred_at")),
                "contracts": abs(_decimal(row.get("option_quantity"))),
                "action": event_type,
                "status": "EXPIRED" if event_type == "expiration" else "ASSIGNED",
                "net_cash": ZERO,
                "sort_order": 2,
            }
        )
    records.sort(
        key=lambda item: (
            _date(item["occurred_at"]),
            item["order_key"],
            item["sort_order"],
            item["occurred_at"],
            item["record_key"],
        )
    )
    return records, exclusions


def _long_option_inventory(
    executions: Sequence[Mapping[str, object]],
) -> defaultdict[str, list[tuple[datetime, Decimal]]]:
    inventory: defaultdict[str, list[tuple[datetime, Decimal]]] = defaultdict(list)
    for row in sorted(executions, key=lambda item: _datetime(item.get("occurred_at"))):
        if str(row.get("asset_type")) != "option":
            continue
        side = str(row.get("side"))
        effect = str(row.get("position_effect"))
        if (side, effect) not in {("buy", "opening"), ("sell", "closing")}:
            continue
        key = _scoped_key(row, "symbol")
        quantity = abs(_decimal(row.get("quantity")))
        if side == "buy":
            inventory[key].append((_datetime(row.get("occurred_at")), quantity))
            continue
        remaining = quantity
        for index, (opened_at, available) in enumerate(inventory[key]):
            consumed = min(available, remaining)
            inventory[key][index] = (opened_at, available - consumed)
            remaining -= consumed
            if remaining <= ZERO:
                break
    return inventory


def _consume_long_inventory(
    inventory: Mapping[str, list[tuple[datetime, Decimal]]],
    row: Mapping[str, object],
) -> bool:
    lots = inventory.get(_scoped_key(row, "symbol"), [])
    occurred_at = _datetime(row.get("occurred_at"))
    quantity = abs(_decimal(row.get("option_quantity")))
    eligible = sum(
        (available for opened_at, available in lots if opened_at <= occurred_at),
        ZERO,
    )
    if quantity <= ZERO or eligible < quantity:
        return False
    remaining = quantity
    for index, (opened_at, available) in enumerate(lots):
        if opened_at > occurred_at:
            continue
        consumed = min(available, remaining)
        lots[index] = (opened_at, available - consumed)
        remaining -= consumed
        if remaining <= ZERO:
            break
    return True


def _single_active_campaign(lots: Sequence[_ActiveLot]) -> str | None:
    campaign_ids = {lot.campaign_id for lot in lots if lot.contracts > ZERO}
    return next(iter(campaign_ids)) if len(campaign_ids) == 1 else None


def _consume_single_campaign(
    lots: list[_ActiveLot],
    contracts: Decimal,
) -> tuple[str | None, CampaignLinkConfidence]:
    if contracts <= ZERO or not lots:
        return (None, CampaignLinkConfidence.UNKNOWN)
    campaign_ids = {lot.campaign_id for lot in lots if lot.contracts > ZERO}
    available = sum((lot.contracts for lot in lots), ZERO)
    if contracts > available:
        return (None, CampaignLinkConfidence.UNKNOWN)
    if len(campaign_ids) == 1:
        campaign_id = next(iter(campaign_ids))
        confidence = CampaignLinkConfidence.EXACT
    elif contracts <= lots[0].contracts:
        # Listed contracts of one series are fungible. When separate campaign
        # lots overlap, FIFO is an explicit inference—not broker-supplied truth.
        campaign_id = lots[0].campaign_id
        confidence = CampaignLinkConfidence.INFERRED
    else:
        return (None, CampaignLinkConfidence.UNKNOWN)
    remaining = contracts
    while lots and remaining > ZERO:
        lot = lots[0]
        consumed = min(lot.contracts, remaining)
        lot.contracts -= consumed
        remaining -= consumed
        if lot.contracts == ZERO:
            lots.pop(0)
    return (campaign_id, confidence)


def _campaign_has_open_contracts(
    active: Mapping[str, list[_ActiveLot]],
    campaign_id: str,
) -> bool:
    return any(
        lot.campaign_id == campaign_id and lot.contracts > ZERO
        for lots in active.values()
        for lot in lots
    )


def _scoped_key(row: Mapping[str, object], field_name: str) -> str:
    value = str(row.get(field_name) or "")
    if not value:
        return ""
    return f"{row.get('account_mask') or 'default'}:{value}"


def campaign_record_key(row: Mapping[str, object]) -> str:
    """Stable annotation key for an execution or lifecycle row.

    Must stay identical wherever surviving lots are matched back to the ledger.
    """

    external_key = str(row.get("external_key"))
    account_mask = str(row.get("account_mask") or "")
    return f"{account_mask}:{external_key}" if account_mask else external_key


def _record_key(row: Mapping[str, object]) -> str:
    return campaign_record_key(row)


def _weaker(
    left: CampaignLinkConfidence,
    right: CampaignLinkConfidence,
) -> CampaignLinkConfidence:
    rank = {
        CampaignLinkConfidence.EXACT: 0,
        CampaignLinkConfidence.USER_CONFIRMED: 1,
        CampaignLinkConfidence.INFERRED: 2,
        CampaignLinkConfidence.UNKNOWN: 3,
    }
    return left if rank[left] >= rank[right] else right


def _date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    return datetime.fromisoformat(str(value))


def _decimal(value: object) -> Decimal:
    return ZERO if value is None else Decimal(str(value))
