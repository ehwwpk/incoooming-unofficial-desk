from __future__ import annotations

from sqlalchemy.orm import Session

from schwab_dashboard.application.ports.repositories import (
    AccountBalanceSnapshotRepository,
    AccountRepository,
    PositionSnapshotRepository,
    RawEventRepository,
    ReconciliationRepository,
    SyncRunRepository,
    UnitOfWork,
    UnitOfWorkFactory,
)
from schwab_dashboard.infrastructure.database.engine import SessionFactory
from schwab_dashboard.infrastructure.database.repositories import (
    SqlAccountBalanceSnapshotRepository,
    SqlAccountRepository,
    SqlPositionSnapshotRepository,
    SqlRawEventRepository,
    SqlReconciliationRepository,
    SqlSyncRunRepository,
)


class SqlAlchemyUnitOfWork:
    sync_runs: SyncRunRepository
    raw_events: RawEventRepository
    accounts: AccountRepository
    balances: AccountBalanceSnapshotRepository
    positions: PositionSnapshotRepository
    reconciliation: ReconciliationRepository

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> UnitOfWork:
        self._session = self._session_factory()
        self.sync_runs = SqlSyncRunRepository(self._session)
        self.raw_events = SqlRawEventRepository(self._session)
        self.accounts = SqlAccountRepository(self._session)
        self.balances = SqlAccountBalanceSnapshotRepository(self._session)
        self.positions = SqlPositionSnapshotRepository(self._session)
        self.reconciliation = SqlReconciliationRepository(self._session)
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        del exc_type, exc_value, traceback
        if self._session is not None:
            self._session.rollback()
            self._session.close()
            self._session = None

    def commit(self) -> None:
        self._require_session().commit()

    def rollback(self) -> None:
        self._require_session().rollback()

    def _require_session(self) -> Session:
        if self._session is None:
            raise RuntimeError("Unit of work has not been entered")
        return self._session


def build_uow_factory(session_factory: SessionFactory) -> UnitOfWorkFactory:
    def factory() -> UnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    return factory
