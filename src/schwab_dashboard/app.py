from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from schwab_dashboard.api.routes.dashboard import router as dashboard_router
from schwab_dashboard.api.routes.health import router as health_router
from schwab_dashboard.container import Container


def create_app(container: Container | None = None) -> FastAPI:
    owns_container = container is None
    app_container = container or Container()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        del app
        yield
        if owns_container:
            app_container.close()

    app = FastAPI(
        title="Incomming Unofficial Desk",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.container = app_container
    static_dir = Path(__file__).resolve().parent / "web" / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
    app.include_router(health_router)
    app.include_router(dashboard_router)
    return app
