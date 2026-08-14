from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from schwab_dashboard.domain.instruments import InstrumentRecord, OptionDeliverable
from schwab_dashboard.infrastructure.database.tables.instrument import InstrumentTable


class SqlInstrumentRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert(self, instrument: InstrumentRecord) -> str:
        row = self._session.scalar(
            select(InstrumentTable).where(
                InstrumentTable.source == instrument.source,
                InstrumentTable.external_key == instrument.external_key,
            )
        )
        values = _table_values(instrument)
        if row is None:
            row = InstrumentTable(
                **values,
                first_observed_at=instrument.observed_at,
                last_observed_at=instrument.observed_at,
            )
            self._session.add(row)
        else:
            row.symbol = instrument.symbol
            if instrument.asset_type.value != "unknown" or row.asset_type == "unknown":
                row.asset_type = instrument.asset_type.value
            _update_optional_metadata(row, values)
            if _as_utc(instrument.observed_at) < _as_utc(row.first_observed_at):
                row.first_observed_at = instrument.observed_at
            if _as_utc(instrument.observed_at) > _as_utc(row.last_observed_at):
                row.last_observed_at = instrument.observed_at
        self._session.flush()
        return row.id

    def require_id(self, *, source: str, external_key: str) -> str:
        instrument_id = self._session.scalar(
            select(InstrumentTable.id).where(
                InstrumentTable.source == source,
                InstrumentTable.external_key == external_key,
            )
        )
        if instrument_id is None:
            raise LookupError(f"Instrument {external_key!r} from source {source!r} does not exist")
        return instrument_id


def _table_values(instrument: InstrumentRecord) -> dict[str, Any]:
    return {
        "source": instrument.source,
        "external_key": instrument.external_key,
        "symbol": instrument.symbol,
        "asset_type": instrument.asset_type.value,
        "description": instrument.description,
        "underlying_symbol": instrument.underlying_symbol,
        "option_side": instrument.option_side.value if instrument.option_side is not None else None,
        "expiration_date": instrument.expiration_date,
        "strike": instrument.strike,
        "contract_multiplier": instrument.contract_multiplier,
        "deliverable": _deliverable_payload(instrument.deliverable),
    }


def _update_optional_metadata(row: InstrumentTable, values: dict[str, Any]) -> None:
    for field in (
        "description",
        "underlying_symbol",
        "option_side",
        "expiration_date",
        "strike",
        "contract_multiplier",
        "deliverable",
    ):
        value = values[field]
        if value is not None:
            setattr(row, field, value)


def _deliverable_payload(deliverable: OptionDeliverable | None) -> dict[str, Any] | None:
    if deliverable is None:
        return None
    return {
        "kind": deliverable.kind.value,
        "description": deliverable.description,
        "components": [
            {
                "asset_type": component.asset_type.value,
                "symbol": component.symbol,
                "quantity": _decimal_text(component.quantity),
                "cash_amount": _decimal_text(component.cash_amount),
                "currency": component.currency,
            }
            for component in deliverable.components
        ],
    }


def _decimal_text(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
