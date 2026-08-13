from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from schwab_dashboard.application.errors import SyncValidationError
from schwab_dashboard.application.ports.broker import BrokerAccountRecord
from schwab_dashboard.application.services.sync_accounts import SyncAccountsAndPositions
from schwab_dashboard.domain.broker import BrokerAccount, BrokerPosition
from schwab_dashboard.infrastructure.database.tables import (
    AccountTable,
    PositionSnapshotTable,
    RawBrokerEventTable,
    ReconciliationIssueTable,
    SyncRunTable,
)
from tests.fakes import FakeBrokerGateway


def _position(symbol: str = "XYZ") -> BrokerPosition:
    return BrokerPosition(
        instrument_key=f"instrument-{symbol}",
        symbol=symbol,
        asset_type="EQUITY",
        long_quantity=Decimal("100"),
        short_quantity=Decimal("0"),
        average_price=Decimal("10.25"),
        market_value=Decimal("1125"),
    )


def _record(*positions: BrokerPosition) -> BrokerAccountRecord:
    return BrokerAccountRecord(
        account=BrokerAccount(
            external_key="hash-account-1",
            account_mask="...1234",
            account_type="MARGIN",
        ),
        positions=tuple(positions),
        raw_payload={"securitiesAccount": {"accountNumber": "redacted"}},
    )


def test_sync_preserves_raw_event_and_normalized_snapshot(
    database_runtime: tuple[object, object, object],
) -> None:
    _, session_factory, uow_factory = database_runtime
    service = SyncAccountsAndPositions(
        broker=FakeBrokerGateway([_record(_position())]),  # type: ignore[arg-type]
        uow_factory=uow_factory,  # type: ignore[arg-type]
        parser_version="test-v1",
    )

    result = service.execute()

    assert result.account_count == 1
    assert result.position_count == 1
    with session_factory() as session:  # type: ignore[operator]
        assert session.scalar(select(func.count()).select_from(SyncRunTable)) == 1
        assert session.scalar(select(func.count()).select_from(RawBrokerEventTable)) == 1
        assert session.scalar(select(func.count()).select_from(AccountTable)) == 1
        assert session.scalar(select(func.count()).select_from(PositionSnapshotTable)) == 1
        run = session.get(SyncRunTable, result.run_id)
        assert run is not None
        assert run.status == "completed"


def test_duplicate_position_identity_fails_without_guessing(
    database_runtime: tuple[object, object, object],
) -> None:
    _, session_factory, uow_factory = database_runtime
    service = SyncAccountsAndPositions(
        broker=FakeBrokerGateway([_record(_position(), _position())]),  # type: ignore[arg-type]
        uow_factory=uow_factory,  # type: ignore[arg-type]
        parser_version="test-v1",
    )

    with pytest.raises(SyncValidationError, match="structural reconciliation"):
        service.execute()

    with session_factory() as session:  # type: ignore[operator]
        assert session.scalar(select(func.count()).select_from(RawBrokerEventTable)) == 1
        assert session.scalar(select(func.count()).select_from(PositionSnapshotTable)) == 0
        assert session.scalar(select(func.count()).select_from(ReconciliationIssueTable)) == 1
        run = session.scalar(select(SyncRunTable))
        assert run is not None
        assert run.status == "failed"


def test_each_real_sync_creates_a_new_observation(
    database_runtime: tuple[object, object, object],
) -> None:
    _, session_factory, uow_factory = database_runtime
    service = SyncAccountsAndPositions(
        broker=FakeBrokerGateway([_record(_position())]),  # type: ignore[arg-type]
        uow_factory=uow_factory,  # type: ignore[arg-type]
        parser_version="test-v1",
    )

    service.execute()
    service.execute()

    with session_factory() as session:  # type: ignore[operator]
        assert session.scalar(select(func.count()).select_from(SyncRunTable)) == 2
        assert session.scalar(select(func.count()).select_from(RawBrokerEventTable)) == 2
        assert session.scalar(select(func.count()).select_from(AccountTable)) == 1
        assert session.scalar(select(func.count()).select_from(PositionSnapshotTable)) == 2


def test_activity_run_does_not_hide_latest_position_snapshot(
    database_runtime: tuple[object, object, object],
) -> None:
    _, _, uow_factory = database_runtime
    service = SyncAccountsAndPositions(
        broker=FakeBrokerGateway([_record(_position())]),  # type: ignore[arg-type]
        uow_factory=uow_factory,  # type: ignore[arg-type]
        parser_version="test-v1",
    )
    service.execute()

    with uow_factory() as uow:  # type: ignore[operator]
        observed_at = datetime.now(UTC)
        activity_run = uow.sync_runs.start(
            source="schwab_activity",
            started_at=observed_at,
        )
        uow.sync_runs.complete(
            activity_run,
            completed_at=observed_at,
            account_count=1,
            position_count=0,
        )
        uow.commit()

    with uow_factory() as uow:  # type: ignore[operator]
        rows = uow.positions.list_latest()

    assert len(rows) == 1
    assert rows[0]["symbol"] == "XYZ"


def test_latest_successful_sync_is_not_replaced_by_a_newer_failed_attempt(
    database_runtime: tuple[object, object, object],
) -> None:
    _, _, uow_factory = database_runtime
    succeeded_at = datetime.now(UTC) - timedelta(minutes=5)
    failed_at = datetime.now(UTC)

    with uow_factory() as uow:  # type: ignore[operator]
        successful_run = uow.sync_runs.start(source="schwab", started_at=succeeded_at)
        uow.sync_runs.complete(
            successful_run,
            completed_at=succeeded_at,
            account_count=1,
            position_count=24,
        )
        failed_run = uow.sync_runs.start(source="schwab", started_at=failed_at)
        uow.sync_runs.fail(
            failed_run,
            completed_at=failed_at,
            error_message="authorization unavailable",
        )
        uow.commit()

    with uow_factory() as uow:  # type: ignore[operator]
        latest_attempt = uow.sync_runs.latest()
        latest_success = uow.sync_runs.latest_successful(source="schwab")

    assert latest_attempt is not None
    assert latest_attempt.run_id == failed_run
    assert latest_attempt.status == "failed"
    assert latest_success is not None
    assert latest_success.run_id == successful_run
    assert latest_success.status == "completed"
