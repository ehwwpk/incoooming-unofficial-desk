from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from schwab_dashboard.domain.workspace import (
    FilterPreference,
    SortDirection,
    SplitPreference,
    TablePreference,
    WorkspaceDensity,
    WorkspaceKey,
    WorkspacePreferences,
)
from schwab_dashboard.infrastructure.database.tables.workspace import WorkspacePreferenceTable


class SqlWorkspaceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def save(self, *, owner_key: str, preferences: WorkspacePreferences) -> str:
        row = self._session.scalar(
            select(WorkspacePreferenceTable).where(
                WorkspacePreferenceTable.owner_key == owner_key,
                WorkspacePreferenceTable.workspace_key == preferences.workspace_key.value,
            )
        )
        payload = _serialize(preferences)
        if row is None:
            row = WorkspacePreferenceTable(
                owner_key=owner_key,
                workspace_key=preferences.workspace_key.value,
                schema_version=preferences.schema_version,
                payload=payload,
            )
            self._session.add(row)
        else:
            row.schema_version = preferences.schema_version
            row.payload = payload
        self._session.flush()
        return row.id

    def load(
        self,
        *,
        owner_key: str,
        workspace_key: WorkspaceKey,
    ) -> WorkspacePreferences | None:
        row = self._session.scalar(
            select(WorkspacePreferenceTable).where(
                WorkspacePreferenceTable.owner_key == owner_key,
                WorkspacePreferenceTable.workspace_key == workspace_key.value,
            )
        )
        return _deserialize(row.payload) if row is not None else None


def _serialize(preferences: WorkspacePreferences) -> dict[str, Any]:
    return {
        "workspace_key": preferences.workspace_key.value,
        "title": preferences.title,
        "panel_order": list(preferences.panel_order),
        "hidden_panels": list(preferences.hidden_panels),
        "splits": [
            {
                "splitter_key": item.splitter_key,
                "primary_percent": str(item.primary_percent),
            }
            for item in preferences.splits
        ],
        "tables": [
            {
                "table_key": item.table_key,
                "visible_columns": list(item.visible_columns),
                "sort_column": item.sort_column,
                "sort_direction": (
                    item.sort_direction.value if item.sort_direction is not None else None
                ),
            }
            for item in preferences.tables
        ],
        "filters": [
            {"filter_key": item.filter_key, "values": list(item.values)}
            for item in preferences.filters
        ],
        "density": preferences.density.value,
        "reduced_motion": preferences.reduced_motion,
        "high_contrast": preferences.high_contrast,
        "schema_version": preferences.schema_version,
    }


def _deserialize(payload: dict[str, Any]) -> WorkspacePreferences:
    return WorkspacePreferences(
        workspace_key=WorkspaceKey(str(payload["workspace_key"])),
        title=str(payload["title"]),
        panel_order=tuple(str(value) for value in payload["panel_order"]),
        hidden_panels=tuple(str(value) for value in payload.get("hidden_panels", [])),
        splits=tuple(
            SplitPreference(
                splitter_key=str(item["splitter_key"]),
                primary_percent=Decimal(str(item["primary_percent"])),
            )
            for item in payload.get("splits", [])
        ),
        tables=tuple(_table_preference(item) for item in payload.get("tables", [])),
        filters=tuple(
            FilterPreference(
                filter_key=str(item["filter_key"]),
                values=tuple(str(value) for value in item.get("values", [])),
            )
            for item in payload.get("filters", [])
        ),
        density=WorkspaceDensity(str(payload.get("density", "compact"))),
        reduced_motion=bool(payload.get("reduced_motion", False)),
        high_contrast=bool(payload.get("high_contrast", False)),
        schema_version=int(payload["schema_version"]),
    )


def _table_preference(payload: dict[str, Any]) -> TablePreference:
    direction = payload.get("sort_direction")
    return TablePreference(
        table_key=str(payload["table_key"]),
        visible_columns=tuple(str(value) for value in payload["visible_columns"]),
        sort_column=str(payload["sort_column"]) if payload.get("sort_column") is not None else None,
        sort_direction=SortDirection(str(direction)) if direction is not None else None,
    )
