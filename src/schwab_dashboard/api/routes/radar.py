from __future__ import annotations

from dataclasses import asdict
from datetime import date
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from schwab_dashboard.api.dependencies import get_container
from schwab_dashboard.api.source_context import selected_source_key
from schwab_dashboard.application.opportunities.symbol import normalize_symbol
from schwab_dashboard.application.services.run_premium_radar import (
    RadarLookupError,
    RadarRollRequest,
)
from schwab_dashboard.container import Container
from schwab_dashboard.domain.opportunity import RadarMode, RadarPolicy

router = APIRouter(prefix="/api/v1/radar", tags=["radar"])
ContainerDependency = Annotated[Container, Depends(get_container)]


class RollReviewRequest(BaseModel):
    source_option_symbol: str = Field(min_length=1, max_length=64)
    target_expiration: date
    target_strike: Decimal = Field(gt=0)


class LookupRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    mode: RadarMode
    roll: RollReviewRequest | None = None


class PolicyRequest(BaseModel):
    mode: RadarMode
    minimum_dte: int = Field(default=5, ge=0)
    maximum_dte: int = Field(default=60, ge=0)
    minimum_annualized_rate_percent: Decimal = Field(default=Decimal("5"), ge=Decimal("0"))
    minimum_strike: Decimal | None = Field(default=None, ge=0)
    minimum_strike_distance_percent: Decimal = Field(default=Decimal("0"), ge=0)
    maximum_effective_entry: Decimal | None = Field(default=None, ge=0)
    maximum_spread_percent: Decimal = Field(default=Decimal("25"), ge=0)
    minimum_open_interest: int = Field(default=0, ge=0)
    minimum_volume: int = Field(default=0, ge=0)
    maximum_quote_age_seconds: int = Field(default=86400, ge=30, le=86400)
    allowed_contracts: int = Field(default=1, ge=0, le=1000)
    reserved_cash: Decimal = Field(default=Decimal("0"), ge=0)
    maximum_five_day_move_percent: Decimal | None = Field(default=Decimal("20"), ge=0)


class SavedSymbolRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)


@router.post("/lookups")
def run_lookup(
    payload: LookupRequest,
    request: Request,
    container: ContainerDependency,
) -> dict[str, Any]:
    try:
        snapshot = container.read_dashboard(selected_source_key(request)).execute()
        projection = container.premium_radar().execute(
            symbol=payload.symbol,
            mode=payload.mode,
            snapshot=snapshot,
            roll_request=(RadarRollRequest(**payload.roll.model_dump()) if payload.roll else None),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except RadarLookupError as exc:
        status_code = {
            "authorization_required": status.HTTP_401_UNAUTHORIZED,
            "unsupported": status.HTTP_422_UNPROCESSABLE_ENTITY,
        }.get(exc.state, status.HTTP_502_BAD_GATEWAY)
        raise HTTPException(
            status_code=status_code,
            detail={"message": str(exc), "lookup_id": exc.lookup_id, "state": exc.state},
        ) from exc
    return _encode(asdict(projection))


@router.get("/lookups/{lookup_id}")
def read_lookup(lookup_id: str, container: ContainerDependency) -> dict[str, Any]:
    result = container.premium_radar().load_lookup(lookup_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Radar lookup not found")
    return _encode(result)


@router.get("/policies/{symbol}")
def read_policy(
    symbol: str,
    mode: RadarMode,
    container: ContainerDependency,
) -> dict[str, Any]:
    try:
        policy = container.premium_radar().policy_for(symbol=symbol, mode=mode)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _encode(asdict(policy))


@router.put("/policies/{symbol}")
def save_policy(
    symbol: str,
    payload: PolicyRequest,
    container: ContainerDependency,
) -> dict[str, Any]:
    try:
        policy = container.premium_radar().save_policy(
            RadarPolicy(symbol=normalize_symbol(symbol), **payload.model_dump())
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _encode(asdict(policy))


@router.get("/symbols")
def list_symbols(request: Request, container: ContainerDependency) -> dict[str, list[str]]:
    radar = container.premium_radar()
    snapshot = container.read_dashboard(selected_source_key(request)).execute()
    return {
        "book": list(radar.held_symbols(snapshot)),
        "saved": list(radar.saved_symbols()),
    }


@router.post("/saved-symbols", status_code=status.HTTP_204_NO_CONTENT)
def save_symbol(payload: SavedSymbolRequest, container: ContainerDependency) -> None:
    try:
        container.premium_radar().save_symbol(payload.symbol)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.delete("/saved-symbols/{symbol}", status_code=status.HTTP_204_NO_CONTENT)
def remove_symbol(symbol: str, container: ContainerDependency) -> None:
    try:
        container.premium_radar().remove_symbol(symbol)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


def _encode(value: Any) -> dict[str, Any]:
    encoded = jsonable_encoder(value, custom_encoder={Decimal: str})
    if not isinstance(encoded, dict):
        raise RuntimeError("Radar encoder returned an unexpected response shape")
    return encoded
