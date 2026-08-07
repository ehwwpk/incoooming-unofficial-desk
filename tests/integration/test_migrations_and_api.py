from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from alembic import command
from sqlalchemy import inspect

from schwab_dashboard.app import create_app
from schwab_dashboard.cli import _alembic_config
from schwab_dashboard.config import Settings
from schwab_dashboard.container import Container


def test_initial_migration_supports_local_api(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path)
    command.upgrade(_alembic_config(settings), "head")
    container = Container(settings)

    try:
        assert container.database_ready()
        assert {
            "accounts",
            "alembic_version",
            "position_snapshots",
            "raw_broker_events",
            "reconciliation_issues",
            "sync_runs",
        } <= set(inspect(container.engine).get_table_names())

        responses = asyncio.run(_request_initial_routes(container))
        live, ready, dashboard, page = responses
        assert live.json() == {"status": "ok"}
        assert ready.json() == {"status": "ready"}
        assert dashboard.status_code == 200
        assert dashboard.json() == {
            "credentials_configured": False,
            "token_available": False,
            "latest_sync": None,
            "accounts": [],
            "positions": [],
        }
        assert page.status_code == 200
        assert "Schwab Options Dashboard" in page.text
    finally:
        container.close()


async def _request_initial_routes(container: Container) -> tuple[httpx.Response, ...]:
    transport = httpx.ASGITransport(app=create_app(container))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return (
            await client.get("/api/v1/health/live"),
            await client.get("/api/v1/health/ready"),
            await client.get("/api/v1/dashboard"),
            await client.get("/"),
        )
