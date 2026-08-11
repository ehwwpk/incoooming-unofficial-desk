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
        catalog, desk, risk, review, volatility, records = asyncio.run(
            _request_workspaces(container)
        )
        assert catalog.status_code == 200
        assert [item["key"] for item in catalog.json()] == [
            "desk",
            "risk",
            "attribution",
            "volatility",
            "records",
        ]
        assert len({item["window_name"] for item in catalog.json()}) == 5

        assert desk.status_code == 200
        assert desk.text.count("data-tools-toggle") == 1
        assert "desk-workspace-launcher" not in desk.text
        assert "function-rail" in desk.text

        assert risk.status_code == 200
        assert "Next expirations" in risk.text
        assert "CALENDAR CLOCK" in risk.text
        assert "STOCKS ·" in risk.text
        assert "MODEL TIME DECAY / DAY" in risk.text
        assert "EARNINGS DATE UNAVAILABLE" in risk.text
        assert "OPEN OWN WINDOW" in risk.text
        assert 'data-workspace-key="risk"' in risk.text
        assert risk.text.count("data-tools-toggle") == 1
        assert "workspace-tabs" not in risk.text
        assert "workspace-directory" not in risk.text
        assert 'class="workspace-breadcrumb"' in risk.text
        assert "BACK TO DESK" in risk.text

        assert review.status_code == 200
        assert "What the strategy paid" in review.text
        assert "EXECUTED CASH" in review.text
        assert "Covered calls versus shares alone" in review.text
        assert "Call campaigns" in review.text
        assert "MONTH BY MONTH" in review.text
        assert "THROUGH AUG 07" in review.text
        assert "Credits and executed debits" in review.text
        assert review.text.count("data-results-cash-series") == 3
        assert 'data-results-cash-period="quarter"' in review.text
        assert 'data-results-cash-period="ytd"' in review.text
        assert 'data-results-cash-period="r365"' in review.text
        assert "DAILY CASH" not in review.text

        assert volatility.status_code == 200
        assert "Historical IV is not yet collected" in volatility.text
        assert "WAITING FOR IV HISTORY" in volatility.text

        assert records.status_code == 200
        assert "Broker portability without fake parity" in records.text
        assert "Multi-broker aggregator" in records.text
        assert "CONDITIONAL" in records.text
        assert "Cash events" in records.text
        assert "EXACT POSTING DATES" in records.text
        assert "Inactive calendar dates are intentionally omitted" in records.text
    finally:
        container.close()


def test_empty_live_ledger_keeps_workspaces_available_before_broker_auth(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path)
    command.upgrade(_alembic_config(settings), "head")
    container = Container(settings)

    try:
        risk, results, volatility = asyncio.run(_request_pre_auth_workspaces(container))
        assert risk.status_code == 200
        assert "No normalized open calls are available" in risk.text
        assert 'data-workspace-key="risk"' in risk.text
        assert results.status_code == 200
        assert "No performance ledger is available yet" in results.text
        assert "Unsupported results remain blank" in results.text
        assert volatility.status_code == 200
        assert "Historical IV is not yet collected" in volatility.text
        assert "DEMO SOURCE" not in volatility.text
    finally:
        container.close()


async def _request_workspaces(
    container: Container,
) -> tuple[
    httpx.Response,
    httpx.Response,
    httpx.Response,
    httpx.Response,
    httpx.Response,
    httpx.Response,
]:
    transport = httpx.ASGITransport(app=create_app(container))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        responses = await asyncio.gather(
            client.get("/api/v1/workspaces"),
            client.get("/"),
            client.get("/workspaces/risk"),
            client.get("/workspaces/attribution"),
            client.get("/workspaces/volatility"),
            client.get("/workspaces/records"),
        )
    return tuple(responses)  # type: ignore[return-value]


async def _request_pre_auth_workspaces(
    container: Container,
) -> tuple[httpx.Response, httpx.Response, httpx.Response]:
    transport = httpx.ASGITransport(app=create_app(container))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        risk, results, volatility = await asyncio.gather(
            client.get("/workspaces/risk"),
            client.get("/workspaces/attribution"),
            client.get("/workspaces/volatility"),
        )
    return risk, results, volatility
