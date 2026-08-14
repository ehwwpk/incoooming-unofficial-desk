from dataclasses import asdict
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder

from schwab_dashboard.api.dependencies import get_container
from schwab_dashboard.api.source_context import selected_source_key
from schwab_dashboard.container import Container

router = APIRouter(prefix="/api/v1/charts", tags=["charts"])
ContainerDependency = Annotated[Container, Depends(get_container)]


@router.get("/{symbol}")
def campaign_chart(
    symbol: str,
    request: Request,
    container: ContainerDependency,
) -> dict[str, Any]:
    source_key = selected_source_key(request)
    if source_key is None:
        raise HTTPException(status_code=409, detail="Choose a data source first.")
    try:
        chart = container.read_campaign_chart(source_key).execute(symbol)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    payload = jsonable_encoder(
        asdict(chart),
        custom_encoder={Decimal: str},
    )
    if not isinstance(payload, dict):
        raise RuntimeError("Campaign chart encoder returned an unexpected response shape.")
    return payload
