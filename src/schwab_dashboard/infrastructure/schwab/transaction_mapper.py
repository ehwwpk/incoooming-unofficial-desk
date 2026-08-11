from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from schwab_dashboard.application.errors import BrokerPayloadError
from schwab_dashboard.domain.instruments import (
    AssetType,
    DeliverableComponent,
    DeliverableKind,
    InstrumentRecord,
    OptionDeliverable,
    OptionSide,
)
from schwab_dashboard.domain.ledger import (
    CashMovementRecord,
    CashMovementType,
    ExecutionRecord,
    ExecutionSide,
    OptionLifecycleEventRecord,
    OptionLifecycleType,
    PositionEffect,
)
from schwab_dashboard.infrastructure.schwab.option_symbol import parse_occ_option_symbol

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class MappedSchwabTransaction:
    instruments: tuple[InstrumentRecord, ...]
    executions: tuple[ExecutionRecord, ...]
    cash_movements: tuple[CashMovementRecord, ...]
    lifecycle_events: tuple[OptionLifecycleEventRecord, ...]


class SchwabTransactionMapper:
    """Normalize observed Schwab activity without inferring nonexistent executions."""

    def map(self, payload: Mapping[str, Any], *, observed_at: datetime) -> MappedSchwabTransaction:
        activity_id = _required_text(payload, "activityId")
        occurred_at = _transaction_time(payload)
        transaction_type = str(payload.get("type") or "").upper()
        items = _mapping_items(payload.get("transferItems"))
        security_items = [item for item in items if _asset_type(item) != "CURRENCY"]
        instruments = tuple(_instrument(item, observed_at=observed_at) for item in security_items)

        executions: tuple[ExecutionRecord, ...] = ()
        cash_movements: tuple[CashMovementRecord, ...] = ()
        lifecycle_events: tuple[OptionLifecycleEventRecord, ...] = ()
        if transaction_type == "TRADE":
            executions = self._executions(
                activity_id,
                payload,
                security_items,
                occurred_at=occurred_at,
            )
        elif transaction_type == "RECEIVE_AND_DELIVER":
            lifecycle_events = self._lifecycle_events(
                activity_id,
                payload,
                security_items,
                occurred_at=occurred_at,
            )
        else:
            movement = self._cash_movement(
                activity_id,
                payload,
                transaction_type=transaction_type,
                occurred_at=occurred_at,
            )
            cash_movements = (movement,) if movement is not None else ()

        return MappedSchwabTransaction(
            instruments=_deduplicate_instruments(instruments),
            executions=executions,
            cash_movements=cash_movements,
            lifecycle_events=lifecycle_events,
        )

    @staticmethod
    def _executions(
        activity_id: str,
        payload: Mapping[str, Any],
        items: Sequence[Mapping[str, Any]],
        *,
        occurred_at: datetime,
    ) -> tuple[ExecutionRecord, ...]:
        if not items:
            return ()
        signed_costs = [_decimal(item.get("cost")) for item in items]
        total_security_cash = sum(signed_costs, ZERO)
        transaction_net_cash = _decimal(payload.get("netAmount"), default=total_security_cash)
        cash_adjustment = transaction_net_cash - total_security_cash
        records: list[ExecutionRecord] = []
        for index, (item, signed_cost) in enumerate(zip(items, signed_costs, strict=True)):
            amount = _decimal(item.get("amount"))
            if not amount:
                continue
            instrument = _required_mapping(item, "instrument")
            multiplier = _instrument_multiplier(instrument)
            quantity = abs(amount)
            gross_amount = abs(signed_cost)
            price = _optional_decimal(item.get("price"))
            if price is None and quantity and multiplier:
                price = gross_amount / quantity / multiplier
            adjustment = cash_adjustment if index == 0 else ZERO
            records.append(
                ExecutionRecord(
                    external_key=f"{activity_id}:item:{index}",
                    order_external_key=_optional_text(payload.get("orderId")),
                    instrument_external_key=_instrument_external_key(instrument),
                    occurred_at=occurred_at,
                    side=ExecutionSide.BUY if amount > ZERO else ExecutionSide.SELL,
                    position_effect=_position_effect(item.get("positionEffect")),
                    quantity=quantity,
                    price=price or ZERO,
                    gross_amount=gross_amount,
                    fees=max(ZERO, -adjustment),
                    net_cash=signed_cost + adjustment,
                )
            )
        return tuple(records)

    @staticmethod
    def _cash_movement(
        activity_id: str,
        payload: Mapping[str, Any],
        *,
        transaction_type: str,
        occurred_at: datetime,
    ) -> CashMovementRecord | None:
        if transaction_type == "SMA_ADJUSTMENT":
            return None
        description = str(payload.get("description") or transaction_type or "Broker cash activity")
        movement_type = _cash_movement_type(transaction_type, description)
        return CashMovementRecord(
            external_key=activity_id,
            occurred_at=occurred_at,
            movement_type=movement_type,
            amount=_decimal(payload.get("netAmount")),
            description=description,
        )

    @staticmethod
    def _lifecycle_events(
        activity_id: str,
        payload: Mapping[str, Any],
        items: Sequence[Mapping[str, Any]],
        *,
        occurred_at: datetime,
    ) -> tuple[OptionLifecycleEventRecord, ...]:
        description = str(payload.get("description") or "")
        event_type = _lifecycle_type(description)
        events: list[OptionLifecycleEventRecord] = []
        for index, item in enumerate(items):
            instrument = _required_mapping(item, "instrument")
            if str(instrument.get("assetType") or "").upper() != "OPTION":
                continue
            quantity = abs(_decimal(item.get("amount")))
            if not quantity:
                continue
            events.append(
                OptionLifecycleEventRecord(
                    external_key=f"{activity_id}:item:{index}",
                    option_instrument_external_key=_instrument_external_key(instrument),
                    occurred_at=occurred_at,
                    event_type=event_type,
                    option_quantity=quantity,
                    details={
                        "source_type": "RECEIVE_AND_DELIVER",
                        "position_effect": str(item.get("positionEffect") or "UNKNOWN"),
                        "description": description,
                    },
                )
            )
        return tuple(events)


def _instrument(item: Mapping[str, Any], *, observed_at: datetime) -> InstrumentRecord:
    payload = _required_mapping(item, "instrument")
    symbol = _required_text(payload, "symbol").strip()
    raw_type = str(payload.get("assetType") or "UNKNOWN").upper()
    asset_type = _domain_asset_type(raw_type)
    parsed = parse_occ_option_symbol(symbol) if asset_type is AssetType.OPTION else None
    underlying = _optional_text(payload.get("underlyingSymbol"))
    option_side = _option_side(payload.get("putCall"), parsed.option_type if parsed else None)
    multiplier = _instrument_multiplier(payload) if asset_type is AssetType.OPTION else None
    deliverable = None
    if asset_type is AssetType.OPTION and underlying and multiplier:
        deliverable = OptionDeliverable(
            kind=DeliverableKind.STANDARD,
            components=(
                DeliverableComponent(
                    asset_type=AssetType.EQUITY,
                    symbol=underlying,
                    quantity=multiplier,
                ),
            ),
        )
    return InstrumentRecord(
        source="schwab",
        external_key=_instrument_external_key(payload),
        symbol=symbol,
        asset_type=asset_type,
        observed_at=observed_at,
        description=_optional_text(payload.get("description")),
        underlying_symbol=underlying or (parsed.underlying_symbol if parsed else None),
        option_side=option_side,
        expiration_date=parsed.expiration_date if parsed else None,
        strike=_optional_decimal(payload.get("strikePrice")) or (parsed.strike if parsed else None),
        contract_multiplier=multiplier,
        deliverable=deliverable,
    )


def _cash_movement_type(transaction_type: str, description: str) -> CashMovementType:
    if transaction_type == "DIVIDEND_OR_INTEREST":
        return (
            CashMovementType.INTEREST
            if "INTEREST" in description.upper()
            else CashMovementType.DIVIDEND
        )
    if transaction_type in {
        "ACH_RECEIPT",
        "ACH_DISBURSEMENT",
        "CASH_RECEIPT",
        "CASH_DISBURSEMENT",
        "ELECTRONIC_FUND",
        "WIRE_OUT",
        "WIRE_IN",
        "JOURNAL",
    }:
        return CashMovementType.TRANSFER
    return CashMovementType.OTHER


def _lifecycle_type(description: str) -> OptionLifecycleType:
    normalized = description.upper()
    if "ASSIGN" in normalized:
        return OptionLifecycleType.ASSIGNMENT
    if "EXPIR" in normalized:
        return OptionLifecycleType.EXPIRATION
    if "EXERCISE" in normalized:
        return OptionLifecycleType.EXERCISE
    return OptionLifecycleType.ADJUSTMENT


def _position_effect(value: Any) -> PositionEffect:
    normalized = str(value or "").upper()
    if normalized == "OPENING":
        return PositionEffect.OPENING
    if normalized == "CLOSING":
        return PositionEffect.CLOSING
    return PositionEffect.UNKNOWN


def _option_side(value: Any, parsed: str | None) -> OptionSide | None:
    normalized = str(value or parsed or "").upper()
    if normalized == "CALL":
        return OptionSide.CALL
    if normalized == "PUT":
        return OptionSide.PUT
    return None


def _domain_asset_type(value: str) -> AssetType:
    return {
        "EQUITY": AssetType.EQUITY,
        "OPTION": AssetType.OPTION,
        "COLLECTIVE_INVESTMENT": AssetType.MUTUAL_FUND,
        "MUTUAL_FUND": AssetType.MUTUAL_FUND,
        "FIXED_INCOME": AssetType.FIXED_INCOME,
    }.get(value, AssetType.UNKNOWN)


def _asset_type(item: Mapping[str, Any]) -> str:
    instrument = item.get("instrument")
    return str(instrument.get("assetType") or "") if isinstance(instrument, Mapping) else ""


def _instrument_multiplier(instrument: Mapping[str, Any]) -> Decimal:
    return _decimal(instrument.get("optionPremiumMultiplier"), default=Decimal("100"))


def _instrument_external_key(instrument: Mapping[str, Any]) -> str:
    for field in ("instrumentId", "cusip", "uniformSymbol", "symbol"):
        value = _optional_text(instrument.get(field))
        if value:
            return value
    raise BrokerPayloadError("Schwab transaction instrument has no stable identity.")


def _transaction_time(payload: Mapping[str, Any]) -> datetime:
    raw = payload.get("time") or payload.get("tradeDate")
    if raw is None:
        raise BrokerPayloadError("Schwab transaction is missing its source timestamp.")
    text = str(raw).strip().replace("Z", "+00:00")
    try:
        value = datetime.fromisoformat(text)
    except ValueError as exc:
        raise BrokerPayloadError("Schwab transaction timestamp is invalid.") from exc
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _mapping_items(value: Any) -> list[Mapping[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise BrokerPayloadError("Schwab transaction transferItems is not a list.")
    if not all(isinstance(item, Mapping) for item in value):
        raise BrokerPayloadError("Schwab transaction contains a malformed transfer item.")
    return list(value)


def _required_mapping(payload: Mapping[str, Any], field: str) -> Mapping[str, Any]:
    value = payload.get(field)
    if not isinstance(value, Mapping):
        raise BrokerPayloadError(f"Schwab transaction is missing {field}.")
    return value


def _required_text(payload: Mapping[str, Any], field: str) -> str:
    value = _optional_text(payload.get(field))
    if value is None:
        raise BrokerPayloadError(f"Schwab transaction is missing {field}.")
    return value


def _optional_text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _decimal(value: Any, *, default: Decimal = ZERO) -> Decimal:
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise BrokerPayloadError("Schwab transaction contains a non-numeric value.") from exc


def _optional_decimal(value: Any) -> Decimal | None:
    return None if value is None else _decimal(value)


def _deduplicate_instruments(
    instruments: Sequence[InstrumentRecord],
) -> tuple[InstrumentRecord, ...]:
    by_key: dict[str, InstrumentRecord] = {}
    for instrument in instruments:
        by_key[instrument.external_key] = instrument
    return tuple(by_key.values())
