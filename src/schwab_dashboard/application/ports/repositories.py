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
    description: str = ""
    underlying_symbol: str | None = None
    option_type: str | None = None
    expiration_date: datetime | None = None
    strike: Decimal | None = None
    long_open_profit_loss: Decimal | None = None
    short_open_profit_loss: Decimal | None = None


@dataclass(frozen=True, slots=True)
class AccountBalanceSnapshotWrite:
    account_id: str
    sync_run_id: str
    raw_event_id: str
    observed_at: datetime
    liquidation_value: Decimal | None = None
    initial_liquidation_value: Decimal | None = None
    equity: Decimal | None = None
    cash_balance: Decimal | None = None
    money_market_fund: Decimal | None = None
    margin_balance: Decimal | None = None
    buying_power: Decimal | None = None
    available_funds: Decimal | None = None
    maintenance_requirement: Decimal | None = None
    long_market_value: Decimal | None = None
    short_market_value: Decimal | None = None
    long_option_market_value: Decimal | None = None
    short_option_market_value: Decimal | None = None
    is_portfolio_margin: bool = False
    is_intraday_margin: bool = False


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

    def latest_for_source(self, *, source: str) -> SyncRunSummary | None: ...

    def latest_successful(self, *, source: str) -> SyncRunSummary | None: ...


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

    def list_recent_market_symbols(self, *, since: datetime) -> Sequence[str]: ...


class AccountBalanceSnapshotRepository(Protocol):
    def add(self, snapshot: AccountBalanceSnapshotWrite) -> str: ...

    def list_latest(self) -> Sequence[dict[str, Any]]: ...


class ReconciliationRepository(Protocol):
    def add_many(self, sync_run_id: str, issues: Sequence[ReconciliationIssue]) -> None: ...


class UnitOfWork(Protocol):
    sync_runs: SyncRunRepository
    raw_events: RawEventRepository
    accounts: AccountRepository
    positions: PositionSnapshotRepository
    balances: AccountBalanceSnapshotRepository
    reconciliation: ReconciliationRepository

    def __enter__(self) -> UnitOfWork: ...

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


UnitOfWorkFactory = Callable[[], UnitOfWork]
