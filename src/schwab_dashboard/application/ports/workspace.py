from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from schwab_dashboard.domain.workspace import WorkspaceKey, WorkspacePreferences


class WorkspaceRepository(Protocol):
    def save(self, *, owner_key: str, preferences: WorkspacePreferences) -> str: ...

    def load(
        self, *, owner_key: str, workspace_key: WorkspaceKey
    ) -> WorkspacePreferences | None: ...


class WorkspaceUnitOfWork(Protocol):
    workspaces: WorkspaceRepository

    def __enter__(self) -> WorkspaceUnitOfWork: ...

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


WorkspaceUnitOfWorkFactory = Callable[[], WorkspaceUnitOfWork]
