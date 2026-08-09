from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from schwab_dashboard.application.ports.ledger import (
    CashMovementWrite,
    ExecutionWrite,
    OptionLifecycleEventWrite,
)
from schwab_dashboard.infrastructure.database.repositories.idempotency import (
    ensure_immutable_match,
)
from schwab_dashboard.infrastructure.database.tables.ledger import (
    CashMovementTable,
    ExecutionTable,
    OptionLifecycleEventTable,
)


class SqlExecutionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, item: ExecutionWrite) -> str:
        record = item.record
        expected = {
            "instrument_id": item.instrument_id,
            "external_key": record.external_key,
            "order_external_key": record.order_external_key,
            "occurred_at": record.occurred_at,
            "side": record.side.value,
            "position_effect": record.position_effect.value,
            "quantity": record.quantity,
            "price": record.price,
            "gross_amount": record.gross_amount,
            "fees": record.fees,
            "net_cash": record.net_cash,
        }
        row = self._session.scalar(
            select(ExecutionTable).where(
                ExecutionTable.source == item.source,
                ExecutionTable.account_id == item.account_id,
                ExecutionTable.external_key == record.external_key,
            )
        )
        if row is not None:
            ensure_immutable_match(row, expected, identity=f"execution:{record.external_key}")
            return row.id
        row = ExecutionTable(
            source=item.source,
            account_id=item.account_id,
            raw_event_id=item.raw_event_id,
            **expected,
        )
        self._session.add(row)
        self._session.flush()
        return row.id


class SqlCashMovementRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, item: CashMovementWrite) -> str:
        record = item.record
        expected = {
            "instrument_id": item.instrument_id,
            "external_key": record.external_key,
            "occurred_at": record.occurred_at,
            "movement_type": record.movement_type.value,
            "amount": record.amount,
            "description": record.description,
        }
        row = self._session.scalar(
            select(CashMovementTable).where(
                CashMovementTable.source == item.source,
                CashMovementTable.account_id == item.account_id,
                CashMovementTable.external_key == record.external_key,
            )
        )
        if row is not None:
            ensure_immutable_match(row, expected, identity=f"cash:{record.external_key}")
            return row.id
        row = CashMovementTable(
            source=item.source,
            account_id=item.account_id,
            raw_event_id=item.raw_event_id,
            **expected,
        )
        self._session.add(row)
        self._session.flush()
        return row.id


class SqlOptionLifecycleEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, item: OptionLifecycleEventWrite) -> str:
        record = item.record
        expected = {
            "option_instrument_id": item.option_instrument_id,
            "stock_instrument_id": item.stock_instrument_id,
            "external_key": record.external_key,
            "occurred_at": record.occurred_at,
            "event_type": record.event_type.value,
            "option_quantity": record.option_quantity,
            "stock_quantity": record.stock_quantity,
            "cash_amount": record.cash_amount,
            "details": record.details,
        }
        row = self._session.scalar(
            select(OptionLifecycleEventTable).where(
                OptionLifecycleEventTable.source == item.source,
                OptionLifecycleEventTable.account_id == item.account_id,
                OptionLifecycleEventTable.external_key == record.external_key,
            )
        )
        if row is not None:
            ensure_immutable_match(row, expected, identity=f"lifecycle:{record.external_key}")
            return row.id
        row = OptionLifecycleEventTable(
            source=item.source,
            account_id=item.account_id,
            raw_event_id=item.raw_event_id,
            **expected,
        )
        self._session.add(row)
        self._session.flush()
        return row.id
