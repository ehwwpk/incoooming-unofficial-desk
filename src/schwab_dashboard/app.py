from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from schwab_dashboard.api.errors import unhandled_exception
from schwab_dashboard.api.routes.charts import router as charts_router
from schwab_dashboard.api.routes.dashboard import router as dashboard_router
from schwab_dashboard.api.routes.health import router as health_router
from schwab_dashboard.api.routes.radar import router as radar_router
from schwab_dashboard.api.routes.sources import router as sources_router
from schwab_dashboard.api.routes.workspaces import router as workspaces_router
from schwab_dashboard.container import Container
from schwab_dashboard.infrastructure.runtime.auto_sync import AutoSyncWorker
from schwab_dashboard.infrastructure.runtime.identity import new_runtime_identity
from schwab_dashboard.web.security import LocalRequestSecurityMiddleware


def create_app(container: Container | None = None) -> FastAPI:
    owns_container = container is None
    app_container = container or Container()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        worker: AutoSyncWorker | None = None
        if (
            owns_container
            and app_container.settings.auto_sync_enabled
            and not app_container.settings.demo_mode
        ):
            worker = AutoSyncWorker(
                coordinator=app_container.sync_coordinator,
                token_available=app_container.token_available,
                interval_seconds=app_container.settings.auto_sync_interval_seconds,
                startup_delay_seconds=app_container.settings.auto_sync_startup_delay_seconds,
            )
            worker.start()
        app.state.auto_sync_worker = worker
        try:
            yield
        finally:
            if worker is not None:
                await worker.stop()
            if owns_container:
                app_container.close()

    app = FastAPI(
        title="Incoooming",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.container = app_container
    app.state.runtime_identity = new_runtime_identity()
    app.add_exception_handler(Exception, unhandled_exception)
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=[app_container.settings.host, "127.0.0.1", "localhost"],
        www_redirect=False,
    )
    app.add_middleware(LocalRequestSecurityMiddleware)
    static_dir = Path(__file__).resolve().parent / "web" / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.include_router(health_router)
    app.include_router(sources_router)
    app.include_router(charts_router)
    app.include_router(dashboard_router)
    app.include_router(radar_router)
    app.include_router(workspaces_router)
    return app
