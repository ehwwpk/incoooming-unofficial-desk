from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from schwab_dashboard.api.dependencies import get_container
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
    if workspace_key is WorkspaceKey.DESK:
        return RedirectResponse(url="/", status_code=303)
    snapshot = container.read_dashboard().execute()
    return templates.TemplateResponse(
        request=request,
        name="workspace.html",
        context={
            "snapshot": snapshot,
            "workspace": get_workspace(workspace_key),
            "workspaces": list_workspaces(),
            "open_book": build_open_book(snapshot),
            "volatility_rows": build_volatility_rows(snapshot),
            "source_profiles": planned_source_profiles(),
        },
    )
