from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from schwab_dashboard.application.errors import SourceRecordConflictError
from schwab_dashboard.application.services.record_ledger_activity import RecordLedgerActivity
from schwab_dashboard.domain.broker import BrokerAccount
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
    LedgerActivityBatch,
    OptionLifecycleEventRecord,
    OptionLifecycleType,
    PositionEffect,
)
from schwab_dashboard.infrastructure.database.tables import (
    CashMovementTable,
    ExecutionTable,
    InstrumentTable,
    OptionLifecycleEventTable,
)
from schwab_dashboard.infrastructure.database.uow_truth import build_truth_uow_factory

NOW = datetime(2026, 8, 9, 19, 30, tzinfo=UTC)


def _seed_source(uow_factory: object) -> str:
    with uow_factory() as uow:  # type: ignore[operator]
        run_id = uow.sync_runs.start(source="schwab", started_at=NOW)
        raw_event_id = uow.raw_events.add(
            sync_run_id=run_id,
            item_key="transactions:page-1",
            event_type="transactions",
            account_external_key="account-1",
            observed_at=NOW,
            parser_version="test-v1",
            payload={"transactions": ["redacted"]},
        )
        uow.accounts.upsert(
            BrokerAccount(
                external_key="account-1",
                account_mask="...1234",
                account_type="MARGIN",
            ),
            observed_at=NOW,
        )
        uow.commit()
    return raw_event_id


def _instruments() -> tuple[InstrumentRecord, ...]:
    return (
        InstrumentRecord(
            source="schwab",
            external_key="equity-ktos",
            symbol="KTOS",
            asset_type=AssetType.EQUITY,
            observed_at=NOW,
        ),
        InstrumentRecord(
            source="schwab",
            external_key="call-ktos-65",
            symbol="KTOS  260918C00065000",
            asset_type=AssetType.OPTION,
            observed_at=NOW,
            underlying_symbol="KTOS",
            option_side=OptionSide.CALL,
            expiration_date=date(2026, 9, 18),
            strike=Decimal("65"),
            contract_multiplier=Decimal("100"),
            deliverable=OptionDeliverable(
                kind=DeliverableKind.STANDARD,
                components=(
                    DeliverableComponent(
                        asset_type=AssetType.EQUITY,
                        symbol="KTOS",
                        quantity=Decimal("100"),
                    ),
                ),
            ),
        ),
    )


def _batch(raw_event_id: str, *, price: Decimal = Decimal("2.45")) -> LedgerActivityBatch:
    return LedgerActivityBatch(
        source="schwab",
        account_external_key="account-1",
        raw_event_id=raw_event_id,
        instruments=_instruments(),
        executions=(
            ExecutionRecord(
                external_key="fill-1",
                order_external_key="order-1",
                instrument_external_key="call-ktos-65",
                occurred_at=NOW,
                side=ExecutionSide.SELL,
                position_effect=PositionEffect.OPENING,
                quantity=Decimal("5"),
                price=price,
                gross_amount=price * Decimal("500"),
                fees=Decimal("3.25"),
                net_cash=(price * Decimal("500")) - Decimal("3.25"),
            ),
        ),
        cash_movements=(
            CashMovementRecord(
                external_key="cash-div-1",
                instrument_external_key="equity-ktos",
                occurred_at=NOW,
                movement_type=CashMovementType.DIVIDEND,
                amount=Decimal("125.00"),
                description="Qualified dividend",
            ),
        ),
        lifecycle_events=(
            OptionLifecycleEventRecord(
                external_key="assignment-1",
                option_instrument_external_key="call-ktos-65",
                stock_instrument_external_key="equity-ktos",
                occurred_at=NOW,
                event_type=OptionLifecycleType.ASSIGNMENT,
                option_quantity=Decimal("2"),
                stock_quantity=Decimal("200"),
                cash_amount=Decimal("13000"),
                details={"settlement": "physical"},
            ),
        ),
    )


def test_atomic_ledger_is_exact_and_idempotent(
    database_runtime: tuple[object, object, object],
) -> None:
    _, session_factory, existing_uow_factory = database_runtime
    raw_event_id = _seed_source(existing_uow_factory)
    service = RecordLedgerActivity(
        uow_factory=build_truth_uow_factory(session_factory),  # type: ignore[arg-type]
    )

    result = service.execute(_batch(raw_event_id))
    service.execute(_batch(raw_event_id))

    assert result.instrument_count == 2
    assert result.execution_count == 1
    with session_factory() as session:  # type: ignore[operator]
        assert session.scalar(select(func.count()).select_from(InstrumentTable)) == 2
        assert session.scalar(select(func.count()).select_from(ExecutionTable)) == 1
        assert session.scalar(select(func.count()).select_from(CashMovementTable)) == 1
        assert session.scalar(select(func.count()).select_from(OptionLifecycleEventTable)) == 1
        execution = session.scalar(select(ExecutionTable))
        assert execution is not None
        assert execution.net_cash == Decimal("1221.7500000000")
        option = session.scalar(
            select(InstrumentTable).where(InstrumentTable.asset_type == "option")
        )
        assert option is not None
        assert option.deliverable is not None
        assert option.deliverable["components"][0]["quantity"] == "100"


def test_reused_source_identity_with_changed_economics_is_rejected(
    database_runtime: tuple[object, object, object],
) -> None:
    _, session_factory, existing_uow_factory = database_runtime
    raw_event_id = _seed_source(existing_uow_factory)
    service = RecordLedgerActivity(
        uow_factory=build_truth_uow_factory(session_factory),  # type: ignore[arg-type]
    )
    service.execute(_batch(raw_event_id))

    with pytest.raises(SourceRecordConflictError, match="price"):
        service.execute(_batch(raw_event_id, price=Decimal("2.55")))

    with session_factory() as session:  # type: ignore[operator]
        execution = session.scalar(select(ExecutionTable))
        assert execution is not None
        assert execution.price == Decimal("2.4500000000")
