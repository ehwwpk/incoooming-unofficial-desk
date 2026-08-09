from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select

from schwab_dashboard.application.services.workspace_preferences import (
    LoadWorkspacePreferences,
    SaveWorkspacePreferences,
)
from schwab_dashboard.domain.workspace import (
    FilterPreference,
    SortDirection,
    SplitPreference,
    TablePreference,
    WorkspaceDensity,
    WorkspaceKey,
    WorkspacePreferences,
)
from schwab_dashboard.infrastructure.database.tables import WorkspacePreferenceTable
from schwab_dashboard.infrastructure.database.uow_workspace import build_workspace_uow_factory


def _preferences(*, split: str = "44") -> WorkspacePreferences:
    return WorkspacePreferences(
        workspace_key=WorkspaceKey.RISK,
        title="Open risk",
        panel_order=("exposure", "contracts", "scenarios"),
        hidden_panels=("scenarios",),
        splits=(SplitPreference(splitter_key="risk-main", primary_percent=Decimal(split)),),
        tables=(
            TablePreference(
                table_key="open-contracts",
                visible_columns=("symbol", "strike", "dte", "delta", "theta"),
                sort_column="dte",
                sort_direction=SortDirection.ASCENDING,
            ),
        ),
        filters=(FilterPreference(filter_key="account", values=("...1234",)),),
        density=WorkspaceDensity.COMPACT,
        reduced_motion=True,
    )


def test_workspace_preferences_round_trip_and_update_in_place(
    database_runtime: tuple[object, object, object],
) -> None:
    _, session_factory, _ = database_runtime
    factory = build_workspace_uow_factory(session_factory)  # type: ignore[arg-type]
    save = SaveWorkspacePreferences(uow_factory=factory)
    load = LoadWorkspacePreferences(uow_factory=factory)

    preference_id = save.execute(owner_key="local", preferences=_preferences())
    updated_id = save.execute(owner_key="local", preferences=_preferences(split="52"))
    loaded = load.execute(owner_key="local", workspace_key=WorkspaceKey.RISK)

    assert preference_id == updated_id
    assert loaded is not None
    assert loaded.splits[0].primary_percent == Decimal("52")
    assert loaded.tables[0].visible_columns[-1] == "theta"
    assert loaded.reduced_motion is True
    with session_factory() as session:  # type: ignore[operator]
        assert session.scalar(select(func.count()).select_from(WorkspacePreferenceTable)) == 1
