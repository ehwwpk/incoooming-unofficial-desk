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
        assert "Incomming Unofficial Desk" in page.text
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
        assert payload["portfolio"]["total_value"] == "222035.00"
        assert payload["income"]["month"] == "1950.00"
        assert payload["income"]["quarter"] == "6340.00"
        assert payload["covered_calls"]["total_cash_income"] == "7586.00"
        assert payload["covered_calls"]["open_call_credit"] == "3390.00"
        assert payload["covered_calls"]["open_call_mark_value"] == "3188.00"
        assert payload["covered_calls"]["open_mark_profit_loss"] == "202.00"
        assert payload["covered_calls"]["assigned_contracts"] == 2
        assert payload["covered_calls"]["called_away_shares"] == 200
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
        r365 = payload["performance_windows"][-1]
        assert r365["monthly_option_run_rate"] == "2648.33"
        assert r365["monthly_total_run_rate"] == "3084.67"
        assert payload["objective"]["monthly_option_target"] == "3000"
        assert len(payload["basis_lens"]) == 4
        assert payload["basis_lens"][0]["capital_remaining"] == "118310.00"
        assert payload["basis_lens"][0]["recovery_surplus"] == "0"
        assert payload["basis_lens"][0]["fully_recovered"] is False
        assert "MOCK LEDGER / NO SCHWAB WRITES" in page.text
        assert '<span class="brand-mark">IU</span>' in page.text
        assert "WINDOW ACCOUNTING" in page.text
        assert "TRANSACTION CASH · NORMALIZED PACE · OPEN MARK SEPARATED" in page.text
        assert "INTERNAL DESK FEED" not in page.text
        assert "NO MARKET HEADLINES" not in page.text
        assert "R365" in page.text
        assert "$3,000</span> monthly net premium cash" in page.text
        assert 'data-period="month"' in page.text
        assert 'aria-label="Four weeks" aria-selected="true"' in page.text
        assert 'data-period-sheet="month"' in page.text
        assert "data-target-input" in page.text
        assert "DIV RISK // MONITOR" in page.text
        assert "SIM EX-DIV" in page.text
        assert "app.css?v=16" in page.text
        assert "periods.js?v=14" in page.text
        assert 'data-rail-link="portfolio" aria-current="page"' in page.text
        assert "NET PREMIUM CASH / 4 WEEKS" in page.text
        assert "EXECUTED CLOSE / ROLL DEBITS" in page.text
        assert "OPEN-CALL CREDIT RECEIVED" in page.text
        assert "CURRENT OPEN-CALL VALUE" in page.text
        assert "OPEN BOOK · NOT WINDOW CASH" in page.text
        assert 'data-monthly-option-average="$2,648.33"' in page.text
        assert 'data-monthly-total-average="$3,084.67"' in page.text
        assert "data-active-option-average hidden" in page.text
        assert "PREMIUM RECEIVED / CURRENT MARK / OPEN P&amp;L" in page.text
        assert "OPEN P/L AT CURRENT MARK" in page.text
        assert "OPTION VALUE NOW" in page.text
        assert "13W DAILY CLOSES" in page.text
        assert "58 MARKET SESSIONS" in page.text
        assert "YAHOO FINANCE CLOSE" in page.text
        assert 'data-buyback-drag="34.1%"' in page.text
        assert "42.5% executed-debit drag" in page.text
        assert "TIME ELAPSED" in page.text
        assert "RANGE POSITION" in page.text
        assert "2 ASSIGNED / 200 SH" in page.text
        assert "LIFETIME BASIS LENS" in page.text
        assert "ORIGINAL CAPITAL REMAINING" in page.text
        assert "Trades &amp; positions" in page.text
        assert "Covered-call trades" in page.text
        assert "Shares and short calls" in page.text
        assert 'data-record-pane="books" hidden' in page.text
        assert 'data-record-pane="positions" hidden' in page.text
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
