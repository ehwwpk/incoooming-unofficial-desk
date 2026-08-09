from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from schwab_dashboard.domain.broker import BrokerAccount
from schwab_dashboard.domain.reconciliation import ReconciliationIssue


@dataclass(frozen=True, slots=True)
class PositionSnapshotWrite:
    account_id: str
    sync_run_id: str
    raw_event_id: str
    observed_at: datetime
    instrument_key: str
    symbol: str
    asset_type: str
    long_quantity: Decimal
    short_quantity: Decimal
    average_price: Decimal | None
    market_value: Decimal | None
    day_profit_loss: Decimal | None
    day_profit_loss_percent: Decimal | None


@dataclass(frozen=True, slots=True)
class SyncRunSummary:
    run_id: str
    source: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    account_count: int
    position_count: int
    error_message: str | None


class SyncRunRepository(Protocol):
    def start(self, *, source: str, started_at: datetime) -> str: ...

    def complete(
        self,
        run_id: str,
        *,
        completed_at: datetime,
        account_count: int,
        position_count: int,
    ) -> None: ...

    def fail(self, run_id: str, *, completed_at: datetime, error_message: str) -> None: ...

    def latest(self) -> SyncRunSummary | None: ...


class RawEventRepository(Protocol):
    def add(
        self,
        *,
        sync_run_id: str,
        item_key: str,
        event_type: str,
        account_external_key: str,
        observed_at: datetime,
        parser_version: str,
        payload: dict[str, Any],
    ) -> str: ...


class AccountRepository(Protocol):
    def upsert(self, account: BrokerAccount, *, observed_at: datetime) -> str: ...

    def require_id(self, *, source: str, external_account_key: str) -> str: ...

    def list_summaries(self) -> Sequence[dict[str, Any]]: ...


class PositionSnapshotRepository(Protocol):
    def add(self, snapshot: PositionSnapshotWrite) -> str: ...

    def list_latest(self) -> Sequence[dict[str, Any]]: ...


class ReconciliationRepository(Protocol):
    def add_many(self, sync_run_id: str, issues: Sequence[ReconciliationIssue]) -> None: ...


class UnitOfWork(Protocol):
    sync_runs: SyncRunRepository
    raw_events: RawEventRepository
    accounts: AccountRepository
    positions: PositionSnapshotRepository
    reconciliation: ReconciliationRepository

    def __enter__(self) -> UnitOfWork: ...

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


UnitOfWorkFactory = Callable[[], UnitOfWork]
