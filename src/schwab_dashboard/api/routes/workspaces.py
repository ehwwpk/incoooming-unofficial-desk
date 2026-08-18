from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from schwab_dashboard.api.dependencies import get_container
from schwab_dashboard.api.source_context import selected_source_key, source_label
from schwab_dashboard.application.rolls.board import build_roll_board
from schwab_dashboard.application.rolls.catalog import build_roll_source_catalog
from schwab_dashboard.application.workspaces.catalog import get_workspace, list_workspaces
from schwab_dashboard.application.workspaces.projections import (
    build_open_book,
    build_volatility_rows,
)
from schwab_dashboard.application.workspaces.source_profiles import planned_source_profiles
from schwab_dashboard.container import Container
from schwab_dashboard.domain.workspace import WorkspaceKey
from schwab_dashboard.web.rendering import templates

router = APIRouter(tags=["workspaces"])
ContainerDependency = Annotated[Container, Depends(get_container)]


@router.get("/api/v1/workspaces")
def workspace_catalog() -> list[dict[str, Any]]:
    encoded = jsonable_encoder([asdict(item) for item in list_workspaces()])
    if not isinstance(encoded, list):
        raise RuntimeError("Workspace encoder returned an unexpected response shape.")
    return encoded


@router.get("/workspaces/{workspace_key}", response_class=HTMLResponse)
def workspace_page(
    workspace_key: WorkspaceKey,
    request: Request,
    container: ContainerDependency,
) -> Response:
    page_built_at = datetime.now(UTC)
    if workspace_key is WorkspaceKey.DESK:
        return RedirectResponse(url="/", status_code=303)
    if workspace_key is WorkspaceKey.VOLATILITY:
        return RedirectResponse(url="/workspaces/radar", status_code=303)
    source_key = selected_source_key(request)
    if source_key is None:
        return RedirectResponse(url="/sources", status_code=303)
    try:
        snapshot = container.read_dashboard(source_key).execute()
    except LookupError:
        return RedirectResponse(url="/sources", status_code=303)
    dataset = (
        container.source_store.get_dataset(source_key.removeprefix("csv:"))
        if source_key.startswith("csv:")
        else None
    )
    context: dict[str, Any] = {
        "snapshot": snapshot,
        "page_built_at": page_built_at,
        "workspace": get_workspace(workspace_key),
        "workspaces": list_workspaces(),
        "sync_runtime": container.sync_coordinator.status(),
        "active_source_key": source_key,
        "active_source_label": source_label(
            source_key,
            dataset_name=dataset.name if dataset is not None else None,
        ),
    }
    if workspace_key is WorkspaceKey.RISK:
        context["open_book"] = build_open_book(snapshot)
        context["roll_board"] = build_roll_board(snapshot)
    elif workspace_key is WorkspaceKey.RECORDS:
        context["source_profiles"] = planned_source_profiles()
    elif workspace_key is WorkspaceKey.RADAR:
        context["radar_held_symbols"] = container.premium_radar().held_symbols(snapshot)
        context["radar_saved_symbols"] = container.premium_radar().saved_symbols()
        context["radar_roll_sources"] = build_roll_source_catalog(snapshot)
        context["radar_book_pulse"] = {
            row.symbol: row for row in build_volatility_rows(snapshot)
        }
    elif workspace_key is WorkspaceKey.ATTRIBUTION and snapshot.performance_comparison:
        context["performance_comparison_payload"] = jsonable_encoder(
            asdict(snapshot.performance_comparison)
        )
    return templates.TemplateResponse(
        request=request,
        name="workspace.html",
        context=context,
    )
