from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from schwab_dashboard.application.ports.ledger import (
    CashMovementWrite,
    ExecutionWrite,
    OptionLifecycleEventWrite,
)
from schwab_dashboard.infrastructure.database.publication import published_activity_sync_run_ids
from schwab_dashboard.infrastructure.database.repositories.idempotency import (
    ensure_immutable_match,
)
from schwab_dashboard.infrastructure.database.tables.ledger import (
    CashMovementTable,
    ExecutionTable,
    OptionLifecycleEventTable,
)
from schwab_dashboard.infrastructure.database.tables.sync import RawBrokerEventTable, SyncRunTable


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
            _publish_retry(self._session, row, item.raw_event_id)
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
            _publish_retry(self._session, row, item.raw_event_id)
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
            _enrich_lifecycle_delivery(row, expected)
            _ensure_lifecycle_match(row, expected, identity=f"lifecycle:{record.external_key}")
            if (
                "delivery_ambiguous" not in row.details
                and record.details.get("delivery_ambiguous") is True
            ):
                # This flag is a parser-derived safety annotation over the
                # immutable raw event. Older normalized rows predate it, so a
                # one-way false/absent -> true enrichment is safe and prevents
                # the next historical resync from failing permanently.
                row.details = dict(record.details)
            _publish_retry(self._session, row, item.raw_event_id)
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


def _enrich_lifecycle_delivery(
    row: OptionLifecycleEventTable,
    expected: dict[str, Any],
) -> None:
    """Allow source-backed parser upgrades to fill previously unknown delivery facts.

    These columns were added after lifecycle rows already existed. Re-reading the
    same immutable Schwab activity may discover the stock leg and settlement cash;
    accepting only NULL-to-value transitions preserves immutability while allowing
    the safer parser to publish its additional facts.
    """

    changed = False
    for field in ("stock_instrument_id", "stock_quantity", "cash_amount"):
        if getattr(row, field) is None and expected[field] is not None:
            setattr(row, field, expected[field])
            changed = True
    if changed:
        stored_details = dict(row.details)
        expected_details = dict(expected["details"])
        if all(expected_details.get(key) == value for key, value in stored_details.items()):
            row.details = expected_details


def _publish_retry(
    session: Session,
    row: ExecutionTable | CashMovementTable | OptionLifecycleEventTable,
    raw_event_id: str,
) -> None:
    """Move an identical row off a failed source run when a retry observes it."""

    run_id, status = session.execute(
        select(SyncRunTable.id, SyncRunTable.status)
        .join(RawBrokerEventTable, RawBrokerEventTable.sync_run_id == SyncRunTable.id)
        .where(RawBrokerEventTable.id == row.raw_event_id)
    ).one()
    published = published_activity_sync_run_ids(session)
    linked_to_unpublished_run = published is not None and run_id not in published
    if status != "completed" or linked_to_unpublished_run:
        row.raw_event_id = raw_event_id
        session.flush()


def _ensure_lifecycle_match(
    row: OptionLifecycleEventTable,
    expected: dict[str, Any],
    *,
    identity: str,
) -> None:
    expected_details = dict(expected["details"])
    stored_details = dict(row.details)
    allowed_ambiguity_enrichment = (
        "delivery_ambiguous" not in stored_details
        and expected_details.get("delivery_ambiguous") is True
        and stored_details
        == {key: value for key, value in expected_details.items() if key != "delivery_ambiguous"}
    )
    if row.details != expected_details and not allowed_ambiguity_enrichment:
        # Reuse the common error format without weakening comparison of any
        # source-derived lifecycle field.
        ensure_immutable_match(row, {"details": expected_details}, identity=identity)
    ensure_immutable_match(
        row,
        {key: value for key, value in expected.items() if key != "details"},
        identity=identity,
    )
