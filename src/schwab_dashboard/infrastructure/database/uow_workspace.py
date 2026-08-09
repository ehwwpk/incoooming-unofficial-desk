from __future__ import annotations

from sqlalchemy.orm import Session

from schwab_dashboard.application.ports.workspace import (
    WorkspaceRepository,
    WorkspaceUnitOfWork,
    WorkspaceUnitOfWorkFactory,
)
from schwab_dashboard.infrastructure.database.engine import SessionFactory
from schwab_dashboard.infrastructure.database.repositories.workspace import SqlWorkspaceRepository


class SqlAlchemyWorkspaceUnitOfWork:
    workspaces: WorkspaceRepository

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> WorkspaceUnitOfWork:
        self._session = self._session_factory()
        self.workspaces = SqlWorkspaceRepository(self._session)
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


def build_workspace_uow_factory(session_factory: SessionFactory) -> WorkspaceUnitOfWorkFactory:
    def factory() -> WorkspaceUnitOfWork:
        return SqlAlchemyWorkspaceUnitOfWork(session_factory)

    return factory
