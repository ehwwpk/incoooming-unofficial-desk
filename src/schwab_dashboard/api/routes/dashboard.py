import logging
from dataclasses import asdict
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from schwab_dashboard.api.dependencies import get_container
from schwab_dashboard.api.source_context import selected_source_key, source_label
from schwab_dashboard.application.dashboard.overview import build_desk_overview
from schwab_dashboard.application.errors import (
    AuthenticationRequiredError,
    SyncInProgressError,
)
from schwab_dashboard.application.workspaces.catalog import list_workspaces
from schwab_dashboard.container import Container
from schwab_dashboard.web.rendering import templates

router = APIRouter(tags=["dashboard"])
ContainerDependency = Annotated[Container, Depends(get_container)]
LOGGER = logging.getLogger(__name__)


@router.get("/api/v1/dashboard")
def dashboard_data(request: Request, container: ContainerDependency) -> dict[str, Any]:
    source_key = selected_source_key(request)
    if source_key is None:
        raise HTTPException(status_code=409, detail="Choose a data source first.")
    try:
        snapshot = container.read_dashboard(source_key).execute()
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
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
        return asdict(container.sync_full(trigger="api"))
    except AuthenticationRequiredError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    except SyncInProgressError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.get("/api/v1/sync/status")
def sync_status(container: ContainerDependency) -> dict[str, Any]:
    runtime = container.sync_coordinator.status()
    with container.uow_factory() as uow:
        latest_success = uow.sync_runs.latest_successful(source="schwab_full")
        latest_attempt = uow.sync_runs.latest_for_source(source="schwab_full")
        if latest_success is None:
            latest_success = uow.sync_runs.latest_successful(source="schwab")
        if latest_attempt is None:
            latest_attempt = uow.sync_runs.latest()

    token_available = container.token_available()
    persisted_error = (
        latest_attempt.error_message
        if latest_attempt is not None and latest_attempt.status == "failed"
        else None
    )
    error = runtime.last_error or persisted_error
    state = "syncing" if runtime.running else "synced"
    if container.settings.demo_mode:
        state = "demo"
    elif not token_available:
        state = "authorization_required"
    elif error:
        state = "attention"
    elif latest_success is None:
        state = "waiting"

    return {
        **asdict(runtime),
        "state": state,
        "token_available": token_available,
        "latest_successful_at": (
            latest_success.completed_at if latest_success is not None else None
        ),
        "latest_attempt_status": (latest_attempt.status if latest_attempt is not None else None),
        "latest_attempt_error": persisted_error,
    }


@router.get("/", response_class=HTMLResponse)
def home(request: Request, container: ContainerDependency) -> Response:
    source_key = selected_source_key(request)
    if source_key is None:
        return RedirectResponse(url="/sources", status_code=status.HTTP_303_SEE_OTHER)
    try:
        snapshot = container.read_dashboard(source_key).execute()
    except LookupError:
        return RedirectResponse(url="/sources", status_code=status.HTTP_303_SEE_OTHER)
    dataset = (
        container.source_store.get_dataset(source_key.removeprefix("csv:"))
        if source_key.startswith("csv:")
        else None
    )
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "snapshot": snapshot,
            "desk_overview": build_desk_overview(snapshot),
            "workspaces": list_workspaces(),
            "sync_runtime": container.sync_coordinator.status(),
            "active_source_key": source_key,
            "active_source_label": source_label(
                source_key,
                dataset_name=dataset.name if dataset is not None else None,
            ),
            "schwab_credentials_configured": (container.settings.schwab_credentials_configured),
            "campaign_chart_enabled": container.settings.campaign_chart_enabled,
        },
    )


@router.post("/sync", response_class=RedirectResponse)
def sync_from_browser(container: ContainerDependency) -> RedirectResponse:
    try:
        container.sync_full(trigger="browser")
    except AuthenticationRequiredError:
        return RedirectResponse(url="/?sync=authorization", status_code=status.HTTP_303_SEE_OTHER)
    except SyncInProgressError:
        return RedirectResponse(url="/?sync=busy", status_code=status.HTTP_303_SEE_OTHER)
    except Exception:
        LOGGER.exception("Browser-triggered Schwab sync failed")
        return RedirectResponse(url="/?sync=failed", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/?sync=complete", status_code=status.HTTP_303_SEE_OTHER)
