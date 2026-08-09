from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from schwab_dashboard.domain.validation import require_text


class WorkspaceKey(StrEnum):
    DESK = "desk"
    RISK = "risk"
    ATTRIBUTION = "attribution"
    VOLATILITY = "volatility"
    RECORDS = "records"


class WorkspaceDensity(StrEnum):
    COMPACT = "compact"
    COMFORTABLE = "comfortable"


class SortDirection(StrEnum):
    ASCENDING = "ascending"
    DESCENDING = "descending"


@dataclass(frozen=True, slots=True)
class SplitPreference:
    splitter_key: str
    primary_percent: Decimal

    def __post_init__(self) -> None:
        require_text(self.splitter_key, "splitter_key")
        if not Decimal("20") <= self.primary_percent <= Decimal("80"):
            raise ValueError("primary_percent must be between 20 and 80")


@dataclass(frozen=True, slots=True)
class TablePreference:
    table_key: str
    visible_columns: tuple[str, ...]
    sort_column: str | None = None
    sort_direction: SortDirection | None = None

    def __post_init__(self) -> None:
        require_text(self.table_key, "table_key")
        if not self.visible_columns:
            raise ValueError("visible_columns must not be empty")
        for column in self.visible_columns:
            require_text(column, "visible_column")
        if self.sort_column is not None:
            require_text(self.sort_column, "sort_column")
        if (self.sort_column is None) != (self.sort_direction is None):
            raise ValueError("sort_column and sort_direction must be supplied together")


@dataclass(frozen=True, slots=True)
class FilterPreference:
    filter_key: str
    values: tuple[str, ...]

    def __post_init__(self) -> None:
        require_text(self.filter_key, "filter_key")
        for value in self.values:
            require_text(value, "filter_value")


@dataclass(frozen=True, slots=True)
class WorkspacePreferences:
    workspace_key: WorkspaceKey
    title: str
    panel_order: tuple[str, ...]
    hidden_panels: tuple[str, ...] = ()
    splits: tuple[SplitPreference, ...] = ()
    tables: tuple[TablePreference, ...] = ()
    filters: tuple[FilterPreference, ...] = ()
    density: WorkspaceDensity = WorkspaceDensity.COMPACT
    reduced_motion: bool = False
    high_contrast: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError(f"unsupported workspace schema version: {self.schema_version}")
        require_text(self.title, "title")
        if not self.panel_order:
            raise ValueError("panel_order must not be empty")
        if len(set(self.panel_order)) != len(self.panel_order):
            raise ValueError("panel_order must not contain duplicates")
        unknown_hidden = set(self.hidden_panels) - set(self.panel_order)
        if unknown_hidden:
            raise ValueError("hidden_panels must be present in panel_order")
