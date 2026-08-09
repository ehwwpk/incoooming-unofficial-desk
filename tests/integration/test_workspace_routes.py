from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from alembic import command

from schwab_dashboard.app import create_app
from schwab_dashboard.cli import _alembic_config
from schwab_dashboard.config import Settings
from schwab_dashboard.container import Container


def test_demo_workspaces_have_independent_routes_and_honest_states(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path, demo_mode=True)
    command.upgrade(_alembic_config(settings), "head")
    container = Container(settings)

    try:
        catalog, risk, review, volatility, records = asyncio.run(_request_workspaces(container))
        assert catalog.status_code == 200
        assert [item["key"] for item in catalog.json()] == [
            "desk",
            "risk",
            "attribution",
            "volatility",
            "records",
        ]
        assert len({item["window_name"] for item in catalog.json()}) == 5

        assert risk.status_code == 200
        assert "Open obligations" in risk.text
        assert "ENTRY CASH ≠ CURRENT LIABILITY" in risk.text
        assert "OPEN OWN WINDOW" in risk.text
        assert 'data-workspace-key="risk"' in risk.text

        assert review.status_code == 200
        assert "Cash results and normalized pace" in review.text
        assert "OPEN MARK EXCLUDED FROM CASH" in review.text

        assert volatility.status_code == 200
        assert "Historical IV is not yet collected" in volatility.text
        assert "WAITING FOR IV HISTORY" in volatility.text

        assert records.status_code == 200
        assert "Broker portability without fake parity" in records.text
        assert "Multi-broker aggregator" in records.text
        assert "CONDITIONAL" in records.text
    finally:
        container.close()


def test_empty_live_ledger_keeps_workspaces_available_before_broker_auth(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path)
    command.upgrade(_alembic_config(settings), "head")
    container = Container(settings)

    try:
        risk, volatility = asyncio.run(_request_pre_auth_workspaces(container))
        assert risk.status_code == 200
        assert "No normalized open calls are available" in risk.text
        assert 'data-workspace-key="risk"' in risk.text
        assert volatility.status_code == 200
        assert "Historical IV is not yet collected" in volatility.text
        assert "DEMO SOURCE" not in volatility.text
    finally:
        container.close()


async def _request_workspaces(
    container: Container,
) -> tuple[httpx.Response, httpx.Response, httpx.Response, httpx.Response, httpx.Response]:
    transport = httpx.ASGITransport(app=create_app(container))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        responses = await asyncio.gather(
            client.get("/api/v1/workspaces"),
            client.get("/workspaces/risk"),
            client.get("/workspaces/attribution"),
            client.get("/workspaces/volatility"),
            client.get("/workspaces/records"),
        )
    return tuple(responses)  # type: ignore[return-value]


async def _request_pre_auth_workspaces(
    container: Container,
) -> tuple[httpx.Response, httpx.Response]:
    transport = httpx.ASGITransport(app=create_app(container))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        risk, volatility = await asyncio.gather(
            client.get("/workspaces/risk"),
            client.get("/workspaces/volatility"),
        )
    return risk, volatility
