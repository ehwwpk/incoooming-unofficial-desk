from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal

from schwab_dashboard.application.campaigns import (
    CampaignLedger,
    OptionCampaign,
    campaign_record_key,
    reconcile_option_campaigns,
)
from schwab_dashboard.application.dashboard.live_option_clocks import remaining_opening_rows
from schwab_dashboard.application.dashboard.models import (
    CampaignSummary,
    LiveOpenOptionPosition,
    LivePositionBook,
    LiveUnderlyingPosition,
)
from schwab_dashboard.application.formatting import compact_decimal
from schwab_dashboard.domain.instruments import OptionSide

ZERO = Decimal("0")
HUNDRED = Decimal("100")
TENTH = Decimal("0.1")
STANDARD_MULTIPLIER = Decimal("100")


def project_campaign_summaries(
    executions: Sequence[Mapping[str, object]],
    lifecycle_events: Sequence[Mapping[str, object]],
    *,
    live_book: LivePositionBook | None,
    as_of: date,
) -> tuple[CampaignSummary, ...]:
    """Project the short-premium ledger into the existing campaign-card schema."""

    ledger = reconcile_option_campaigns(executions, lifecycle_events)
    rows_by_key = _rows_by_key(executions, lifecycle_events)
    lots_by_campaign = _attributed_lots(ledger, executions, live_book)
    underlyings = {
        item.symbol: item for item in (live_book.underlyings if live_book is not None else ())
    }
    summaries = tuple(
        _summary(
            campaign,
            rows_by_key=rows_by_key,
            lots=lots_by_campaign.get(campaign.campaign_id, ()),
            live_underlying=underlyings.get(campaign.symbol),
            as_of=as_of,
        )
        for campaign in ledger.campaigns
    )
    return tuple(
        sorted(
            summaries,
            key=lambda item: (item.status != "OPEN", item.expires_on, item.symbol),
        )
    )


def _summary(
    campaign: OptionCampaign,
    *,
    rows_by_key: Mapping[str, Mapping[str, object]],
    lots: Sequence[LiveOpenOptionPosition],
    live_underlying: LiveUnderlyingPosition | None,
    as_of: date,
) -> CampaignSummary:
    events = tuple(rows_by_key[key] for key in campaign.event_keys if key in rows_by_key)
    openings = tuple(row for row in events if _is_opening_sale(row))
    closings = tuple(row for row in events if _is_closing_buy(row))
    assignments = tuple(row for row in events if str(row.get("event_type")) == "assignment")
    live_symbols = {_canonical(lot.option_symbol) for lot in lots}
    first_opening = openings[0] if openings else (events[0] if events else None)
    last_opening = openings[-1] if openings else first_opening
    initial_strike = _strike(first_opening)
    current_strike = _strike(last_opening)
    first_expiry = _expiration(first_opening) if first_opening is not None else as_of
    last_expiry = (
        max((_expiration(row) for row in (openings or events)), default=as_of) if events else as_of
    )
    multiplier = _multiplier(first_opening)
    max_contracts = _max_contracts(openings or events)
    gross_opening_credit = sum((_gross(row) for row in openings), ZERO)
    closing_debits = sum((_gross(row) for row in closings), ZERO)
    fees = sum((_decimal(row.get("fees")) for row in events), ZERO)
    open_credit = sum((_entry_credit(lot) for lot in lots), ZERO)
    estimated_close_value = sum((_current_value(lot) for lot in lots), ZERO)
    open_mark_profit_loss = sum((_open_mark(lot) for lot in lots), ZERO)
    collateral = _collateral(
        campaign,
        current_strike=current_strike,
        max_contracts=max_contracts,
        multiplier=multiplier,
        live_underlying=live_underlying,
    )
    assigned_qty = sum((_lifecycle_quantity(row) for row in assignments), ZERO)
    return CampaignSummary(
        campaign_id=campaign.campaign_id,
        symbol=campaign.symbol,
        intent_label=("SHORT CALL" if campaign.option_side is OptionSide.CALL else "SHORT PUT"),
        status=campaign.status,
        opened_on=campaign.opened_on,
        expires_on=last_expiry,
        days_to_expiration=max(0, (last_expiry - as_of).days),
        legs=tuple(_leg_label(row, live_symbols=live_symbols) for row in events),
        gross_opening_credit=gross_opening_credit,
        closing_debits=closing_debits,
        fees=fees,
        net_cash_to_date=campaign.net_cash_to_date,
        realized_cash=(campaign.net_cash_to_date if campaign.status != "OPEN" else ZERO),
        open_credit=open_credit,
        estimated_close_value=estimated_close_value,
        open_mark_profit_loss=open_mark_profit_loss,
        initial_strike=initial_strike,
        current_strike=current_strike,
        strike_change=current_strike - initial_strike,
        days_extended=max(0, (last_expiry - first_expiry).days),
        called_away_shares=int(assigned_qty * multiplier),
        effective_exit_price=_effective_exit(assignments, openings, multiplier),
        collateral=collateral,
        cash_on_capital_percent=(
            (campaign.net_cash_to_date / collateral * HUNDRED).quantize(TENTH)
            if collateral
            else ZERO
        ),
        progress_percent=_progress(campaign.status, lots, as_of),
        campaign_label=campaign.campaign_label,
        option_side=campaign.option_side.value,
        confidence=campaign.confidence.value,
    )


def _attributed_lots(
    ledger: CampaignLedger,
    executions: Sequence[Mapping[str, object]],
    live_book: LivePositionBook | None,
) -> dict[str, tuple[LiveOpenOptionPosition, ...]]:
    grouped: dict[str, list[LiveOpenOptionPosition]] = defaultdict(list)
    if live_book is None:
        return {}
    for option in (*live_book.calls, *live_book.puts):
        identities: set[str] = set()
        scoped = _executions_for_account(option.account_mask, executions)
        for row in remaining_opening_rows(option.option_symbol, scoped):
            annotation = ledger.annotation_for(campaign_record_key(row))
            if annotation is not None:
                identities.add(annotation.campaign_id)
        if len(identities) == 1:
            grouped[next(iter(identities))].append(option)
    return {key: tuple(value) for key, value in grouped.items()}


def _executions_for_account(
    account_mask: str,
    executions: Sequence[Mapping[str, object]],
) -> tuple[Mapping[str, object], ...]:
    return tuple(
        row
        for row in executions
        if not str(row.get("account_mask") or "") or str(row.get("account_mask")) == account_mask
    )


def _rows_by_key(
    executions: Sequence[Mapping[str, object]],
    lifecycle_events: Sequence[Mapping[str, object]],
) -> dict[str, Mapping[str, object]]:
    rows: dict[str, Mapping[str, object]] = {}
    for row in (*executions, *lifecycle_events):
        rows[campaign_record_key(row)] = row
    return rows


def _collateral(
    campaign: OptionCampaign,
    *,
    current_strike: Decimal,
    max_contracts: Decimal,
    multiplier: Decimal,
    live_underlying: LiveUnderlyingPosition | None,
) -> Decimal:
    if max_contracts <= ZERO or multiplier <= ZERO:
        return ZERO
    if campaign.option_side is OptionSide.PUT:
        return current_strike * max_contracts * multiplier
    price = None if live_underlying is None else live_underlying.current_price
    if price is None:
        return ZERO
    return _decimal(price) * max_contracts * multiplier


def _progress(
    status: str,
    lots: Sequence[LiveOpenOptionPosition],
    as_of: date,
) -> int:
    if status != "OPEN":
        return 100
    if not lots:
        return 0
    weighted = ZERO
    contracts = 0
    for lot in lots:
        original = lot.original_days_to_expiration
        if original is None:
            sold_on = lot.opened_on or as_of
            original = max(0, (lot.expires_on - sold_on).days)
        elapsed_days = max(0, (as_of - (lot.opened_on or as_of)).days)
        elapsed = (
            min(HUNDRED, Decimal(elapsed_days) / Decimal(original) * HUNDRED)
            if original
            else HUNDRED
        )
        weighted += elapsed * Decimal(lot.contracts)
        contracts += lot.contracts
    if not contracts:
        return 0
    return max(0, min(100, int(weighted / Decimal(contracts))))


def _leg_label(row: Mapping[str, object], *, live_symbols: set[str]) -> str:
    occurred = _date(row.get("occurred_at"))
    quantity = _quantity(row)
    strike = compact_decimal(_strike(row))
    side = "C" if _side(row) == "call" else "P"
    expiry = _expiration(row)
    action = _leg_action(row, live_symbols=live_symbols)
    return f"{occurred:%b %d} · {int(quantity)}x ${strike}{side} · {expiry:%b %d} · {action}"


def _leg_action(row: Mapping[str, object], *, live_symbols: set[str]) -> str:
    event_type = str(row.get("event_type") or "")
    if event_type == "expiration":
        return "EXPIRED"
    if event_type == "assignment":
        return "ASSIGNED"
    if _is_closing_buy(row):
        return "CLOSED"
    if _is_opening_sale(row):
        symbol = _canonical(str(row.get("symbol") or ""))
        return "OPEN" if symbol in live_symbols else "SOLD"
    return str(row.get("side") or "EVENT").upper()


def _entry_credit(lot: LiveOpenOptionPosition) -> Decimal:
    if lot.entry_credit_per_share is None:
        return ZERO
    return lot.entry_credit_per_share * lot.contract_multiplier * Decimal(lot.contracts)


def _current_value(lot: LiveOpenOptionPosition) -> Decimal:
    if lot.estimated_mark_per_share is not None:
        return lot.estimated_mark_per_share * lot.contract_multiplier * Decimal(lot.contracts)
    return abs(lot.market_value or ZERO)


def _open_mark(lot: LiveOpenOptionPosition) -> Decimal:
    if lot.open_profit_loss is not None:
        return lot.open_profit_loss
    return _entry_credit(lot) - _current_value(lot)


def _max_contracts(rows: Sequence[Mapping[str, object]]) -> Decimal:
    return max((_quantity(row) for row in rows), default=ZERO)


def _effective_exit(
    assignments: Sequence[Mapping[str, object]],
    openings: Sequence[Mapping[str, object]],
    multiplier: Decimal,
) -> Decimal | None:
    if not assignments:
        return None
    last = assignments[-1]
    assigned_symbol = str(last.get("symbol") or "")
    source = next(
        (row for row in reversed(openings) if str(row.get("symbol") or "") == assigned_symbol),
        openings[-1] if openings else last,
    )
    return _strike(last) + _premium_per_share(source, multiplier)


def _quantity(row: Mapping[str, object]) -> Decimal:
    if str(row.get("event_type") or "") in {"expiration", "assignment"}:
        return abs(_decimal(row.get("option_quantity")))
    return abs(_decimal(row.get("quantity")))


def _lifecycle_quantity(row: Mapping[str, object]) -> Decimal:
    return abs(_decimal(row.get("option_quantity")))


def _gross(row: Mapping[str, object]) -> Decimal:
    if row.get("gross_amount") is not None:
        return abs(_decimal(row.get("gross_amount")))
    return abs(_decimal(row.get("net_cash")))


def _premium_per_share(row: Mapping[str, object], multiplier: Decimal) -> Decimal:
    if row.get("price") is not None:
        return abs(_decimal(row.get("price")))
    quantity = _quantity(row)
    if quantity <= ZERO or multiplier <= ZERO:
        return ZERO
    return _gross(row) / quantity / multiplier


def _strike(row: Mapping[str, object] | None) -> Decimal:
    if row is None:
        return ZERO
    return _decimal(row.get("strike"))


def _expiration(row: Mapping[str, object] | None) -> date:
    if row is None:
        return date.min
    value = row.get("expiration_date")
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return _date(row.get("occurred_at"))


def _multiplier(row: Mapping[str, object] | None) -> Decimal:
    if row is None:
        return STANDARD_MULTIPLIER
    value = row.get("contract_multiplier")
    if value is None:
        return STANDARD_MULTIPLIER
    multiplier = _decimal(value)
    return multiplier if multiplier > ZERO else STANDARD_MULTIPLIER


def _side(row: Mapping[str, object]) -> str:
    return str(row.get("option_side") or "call").strip().lower()


def _is_opening_sale(row: Mapping[str, object]) -> bool:
    return str(row.get("side")) == "sell" and str(row.get("position_effect")) == "opening"


def _is_closing_buy(row: Mapping[str, object]) -> bool:
    return str(row.get("side")) == "buy" and str(row.get("position_effect")) == "closing"


def _date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _decimal(value: object) -> Decimal:
    return ZERO if value is None else Decimal(str(value))


def _canonical(value: str) -> str:
    return "".join(value.upper().split())
