from __future__ import annotations

from schwab_dashboard.application.ports.workspace import WorkspaceUnitOfWorkFactory
from schwab_dashboard.domain.validation import require_text
from schwab_dashboard.domain.workspace import WorkspaceKey, WorkspacePreferences


class SaveWorkspacePreferences:
    def __init__(self, *, uow_factory: WorkspaceUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, *, owner_key: str, preferences: WorkspacePreferences) -> str:
        require_text(owner_key, "owner_key")
        with self._uow_factory() as uow:
            preference_id = uow.workspaces.save(owner_key=owner_key, preferences=preferences)
            uow.commit()
            return preference_id


class LoadWorkspacePreferences:
    def __init__(self, *, uow_factory: WorkspaceUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(
        self,
        *,
        owner_key: str,
        workspace_key: WorkspaceKey,
    ) -> WorkspacePreferences | None:
        require_text(owner_key, "owner_key")
        with self._uow_factory() as uow:
            return uow.workspaces.load(owner_key=owner_key, workspace_key=workspace_key)
