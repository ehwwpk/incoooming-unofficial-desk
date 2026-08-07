from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from schwab_dashboard.api.dependencies import get_container
from schwab_dashboard.container import Container

router = APIRouter(prefix="/api/v1/health", tags=["health"])
ContainerDependency = Annotated[Container, Depends(get_container)]


@router.get("/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
def ready(container: ContainerDependency) -> dict[str, str]:
    if not container.database_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not ready. Run `schwab-dashboard db-upgrade`.",
        )
    return {"status": "ready"}
