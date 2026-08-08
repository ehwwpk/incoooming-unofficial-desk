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
        payload = dashboard.json()
        assert payload["mode"] == "live"
        assert payload["is_demo"] is False
        assert payload["credentials_configured"] is False
        assert payload["token_available"] is False
        assert payload["latest_sync"] is None
        assert payload["accounts"] == []
        assert payload["positions"] == []
        assert payload["portfolio"]["total_value"] == "0"
        assert payload["income"]["month"] == "0"
        assert page.status_code == 200
        assert "Active income desk" in page.text
        assert "Schwab approval is the only external blocker" in page.text
    finally:
        container.close()


def test_demo_mode_renders_complete_dashboard_without_credentials(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path, demo_mode=True)
    command.upgrade(_alembic_config(settings), "head")
    container = Container(settings)

    try:
        responses = asyncio.run(_request_initial_routes(container))
        _, ready, dashboard, page = responses
        payload = dashboard.json()

        assert ready.status_code == 200
        assert payload["mode"] == "demo"
        assert payload["is_demo"] is True
        assert payload["portfolio"]["total_value"] == "230006.00"
        assert payload["income"]["quarter"] == "6340.00"
        assert payload["covered_calls"]["total_cash_income"] == "7586.00"
        assert len(payload["income_periods"]) == 13
        assert len(payload["campaigns"]) == 3
        assert len(payload["positions"]) == 8
        assert len(payload["call_history"]) == 16
        assert [window["key"] for window in payload["performance_windows"]] == [
            "week",
            "month",
            "quarter",
            "ytd",
            "r365",
        ]
        assert payload["objective"]["monthly_option_target"] == "3000"
        assert len(payload["basis_lens"]) == 4
        assert "MOCK LEDGER / NO SCHWAB WRITES" in page.text
        assert "PERFORMANCE WINDOWS" in page.text
        assert "ROLL 365" in page.text
        assert "$3,000</span> monthly net option cash" in page.text
        assert 'data-period="month" aria-selected="true"' in page.text
        assert 'data-period-sheet="month"' in page.text
        assert "data-target-input" in page.text
        assert "DIV RISK // MONITOR" in page.text
        assert "SIM EX-DIV" in page.text
        assert "periods.js?v=7" in page.text
        assert "OPTION +$ / 4 WEEKS" in page.text
        assert "OPEN CALL CLOCKS" in page.text
        assert "SHORT THETA" in page.text
        assert "13W PRICE TAPE" in page.text
        assert "LIFETIME BASIS LENS" in page.text
        assert "Quarter call-sale ledger" in page.text
        assert "CVX" in page.text
        assert "KTOS" in page.text
        assert "URNM" in page.text
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
