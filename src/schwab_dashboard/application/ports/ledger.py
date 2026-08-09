from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from schwab_dashboard.domain.instruments import InstrumentRecord
from schwab_dashboard.domain.ledger import (
    CashMovementRecord,
    ExecutionRecord,
    OptionLifecycleEventRecord,
)


class AccountIdentityRepository(Protocol):
    def require_id(self, *, source: str, external_account_key: str) -> str: ...


class InstrumentRepository(Protocol):
    def upsert(self, instrument: InstrumentRecord) -> str: ...

    def require_id(self, *, source: str, external_key: str) -> str: ...


@dataclass(frozen=True, slots=True)
class ExecutionWrite:
    source: str
    account_id: str
    instrument_id: str
    raw_event_id: str
    record: ExecutionRecord


@dataclass(frozen=True, slots=True)
class CashMovementWrite:
    source: str
    account_id: str
    instrument_id: str | None
    raw_event_id: str
    record: CashMovementRecord


@dataclass(frozen=True, slots=True)
class OptionLifecycleEventWrite:
    source: str
    account_id: str
    option_instrument_id: str
    stock_instrument_id: str | None
    raw_event_id: str
    record: OptionLifecycleEventRecord


class ExecutionRepository(Protocol):
    def add(self, item: ExecutionWrite) -> str: ...


class CashMovementRepository(Protocol):
    def add(self, item: CashMovementWrite) -> str: ...


class OptionLifecycleEventRepository(Protocol):
    def add(self, item: OptionLifecycleEventWrite) -> str: ...


class TruthUnitOfWork(Protocol):
    accounts: AccountIdentityRepository
    instruments: InstrumentRepository
    executions: ExecutionRepository
    cash_movements: CashMovementRepository
    lifecycle_events: OptionLifecycleEventRepository

    def __enter__(self) -> TruthUnitOfWork: ...

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


TruthUnitOfWorkFactory = Callable[[], TruthUnitOfWork]
