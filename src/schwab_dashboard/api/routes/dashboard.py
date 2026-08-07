from dataclasses import asdict
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from schwab_dashboard.api.dependencies import get_container
from schwab_dashboard.application.errors import AuthenticationRequiredError
from schwab_dashboard.container import Container
from schwab_dashboard.web.rendering import templates

router = APIRouter(tags=["dashboard"])
ContainerDependency = Annotated[Container, Depends(get_container)]


@router.get("/api/v1/dashboard")
def dashboard_data(container: ContainerDependency) -> dict[str, Any]:
    snapshot = container.read_dashboard().execute()
    return {
        "credentials_configured": snapshot.credentials_configured,
        "token_available": snapshot.token_available,
        "latest_sync": asdict(snapshot.latest_sync) if snapshot.latest_sync else None,
        "accounts": snapshot.accounts,
        "positions": snapshot.positions,
    }


@router.post("/api/v1/sync/accounts")
def sync_accounts(container: ContainerDependency) -> dict[str, Any]:
    try:
        return asdict(container.sync_accounts().execute())
    except AuthenticationRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc


@router.get("/", response_class=HTMLResponse)
def home(request: Request, container: ContainerDependency) -> HTMLResponse:
    snapshot = container.read_dashboard().execute()
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"snapshot": snapshot},
    )


@router.post("/sync", response_class=RedirectResponse)
def sync_from_browser(container: ContainerDependency) -> RedirectResponse:
    container.sync_accounts().execute()
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
