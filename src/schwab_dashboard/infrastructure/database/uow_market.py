from __future__ import annotations

from sqlalchemy.orm import Session

from schwab_dashboard.application.ports.ledger import InstrumentRepository
from schwab_dashboard.application.ports.market import (
    MarketUnitOfWork,
    MarketUnitOfWorkFactory,
    OptionMarketSnapshotRepository,
    RawMarketEventRepository,
    UnderlyingDailyBarRepository,
    UnderlyingIntradayBarRepository,
    UnderlyingMarketSnapshotRepository,
)
from schwab_dashboard.infrastructure.database.engine import SessionFactory
from schwab_dashboard.infrastructure.database.repositories import (
    SqlInstrumentRepository,
    SqlOptionMarketSnapshotRepository,
    SqlRawMarketEventRepository,
    SqlUnderlyingDailyBarRepository,
    SqlUnderlyingIntradayBarRepository,
    SqlUnderlyingMarketSnapshotRepository,
)


class SqlAlchemyMarketUnitOfWork:
    instruments: InstrumentRepository
    raw_market_events: RawMarketEventRepository
    underlying_market_snapshots: UnderlyingMarketSnapshotRepository
    option_market_snapshots: OptionMarketSnapshotRepository
    underlying_daily_bars: UnderlyingDailyBarRepository
    underlying_intraday_bars: UnderlyingIntradayBarRepository

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> MarketUnitOfWork:
        self._session = self._session_factory()
        self.instruments = SqlInstrumentRepository(self._session)
        self.raw_market_events = SqlRawMarketEventRepository(self._session)
        self.underlying_market_snapshots = SqlUnderlyingMarketSnapshotRepository(self._session)
        self.option_market_snapshots = SqlOptionMarketSnapshotRepository(self._session)
        self.underlying_daily_bars = SqlUnderlyingDailyBarRepository(self._session)
        self.underlying_intraday_bars = SqlUnderlyingIntradayBarRepository(self._session)
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


def build_market_uow_factory(session_factory: SessionFactory) -> MarketUnitOfWorkFactory:
    def factory() -> MarketUnitOfWork:
        return SqlAlchemyMarketUnitOfWork(session_factory)

    return factory
