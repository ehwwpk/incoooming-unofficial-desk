from dataclasses import asdict
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, RedirectResponse

from schwab_dashboard.api.dependencies import get_container
from schwab_dashboard.application.dashboard.overview import build_desk_overview
from schwab_dashboard.application.errors import AuthenticationRequiredError
from schwab_dashboard.application.workspaces.catalog import list_workspaces
from schwab_dashboard.container import Container
from schwab_dashboard.web.rendering import templates

router = APIRouter(tags=["dashboard"])
ContainerDependency = Annotated[Container, Depends(get_container)]


@router.get("/api/v1/dashboard")
def dashboard_data(container: ContainerDependency) -> dict[str, Any]:
    snapshot = container.read_dashboard().execute()
    payload: dict[str, Any] = asdict(snapshot)
    payload["is_demo"] = snapshot.is_demo
    encoded = jsonable_encoder(payload, custom_encoder={Decimal: str})
    if not isinstance(encoded, dict):
        raise RuntimeError("Dashboard encoder returned an unexpected response shape.")
    return encoded


@router.post("/api/v1/sync/accounts")
def sync_accounts(container: ContainerDependency) -> dict[str, Any]:
    try:
        return asdict(container.sync_accounts().execute())
    except AuthenticationRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.post("/api/v1/sync/full")
def sync_full(container: ContainerDependency) -> dict[str, Any]:
    try:
        accounts = container.sync_accounts().execute()
        activity = container.sync_transactions().execute()
        market = container.sync_market_data().execute()
        return {
            "accounts": asdict(accounts),
            "activity": asdict(activity),
            "market": asdict(market),
        }
    except AuthenticationRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.get("/", response_class=HTMLResponse)
def home(request: Request, container: ContainerDependency) -> HTMLResponse:
    snapshot = container.read_dashboard().execute()
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "snapshot": snapshot,
            "desk_overview": build_desk_overview(snapshot),
            "workspaces": list_workspaces(),
        },
    )


@router.post("/sync", response_class=RedirectResponse)
def sync_from_browser(container: ContainerDependency) -> RedirectResponse:
    container.sync_accounts().execute()
    container.sync_transactions().execute()
    container.sync_market_data().execute()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
