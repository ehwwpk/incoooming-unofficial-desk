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
            "cash_movements",
            "executions",
            "instruments",
            "option_lifecycle_events",
            "option_market_snapshots",
            "position_snapshots",
            "raw_broker_events",
            "raw_market_events",
            "reconciliation_issues",
            "sync_runs",
            "underlying_intraday_bars",
            "underlying_market_snapshots",
            "workspace_preferences",
        } <= set(inspect(container.engine).get_table_names())

        live, ready, dashboard, sync_status, page = asyncio.run(_request_initial_routes(container))
        assert live.json()["status"] == "ok"
        assert live.json()["app"] == "incoooming-local-desk"
        assert isinstance(live.json()["pid"], int)
        assert len(live.json()["build_id"]) == 16
        assert ready.json()["status"] == "ready"
        assert ready.json()["database"] is True
        payload = dashboard.json()
        assert payload["mode"] == "live"
        assert payload["positions"] == []
        assert payload["cash_events"] == []
        assert payload["cash_activity_windows"] == []
        assert payload["cash_chart_series"] == []
        assert payload["policies"] == []
        assert sync_status.status_code == 200
        assert sync_status.json()["state"] == "authorization_required"
        assert sync_status.json()["interval_seconds"] == 900
        assert page.status_code == 200
        assert "data-page-built-at=" in page.text
        assert "This computer does not have Schwab Developer app credentials yet." in page.text
    finally:
        container.close()


def test_demo_mode_renders_operator_plan_without_credentials(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, data_dir=tmp_path, demo_mode=True)
    command.upgrade(_alembic_config(settings), "head")
    container = Container(settings)
    try:
        _, ready, dashboard, sync_status, page = asyncio.run(_request_initial_routes(container))
        payload = dashboard.json()

        assert ready.status_code == 200
        assert sync_status.json()["state"] == "demo"
        assert payload["mode"] == "demo"
        assert payload["portfolio"]["total_value"] == "223485.00"
        assert payload["income"]["month"] == "1805.000"
        assert payload["covered_calls"]["total_shares"] == 2000
        assert payload["covered_calls"]["open_call_credit"] == "3390.000"
        assert payload["covered_calls"]["open_call_mark_value"] == "1738.00"
        assert payload["covered_calls"]["open_mark_profit_loss"] == "1652.000"
        assert len(payload["positions"]) == 9
        assert len(payload["call_history"]) == 17
        assert len(payload["campaigns"]) == 13
        assert sum(item["status"] == "OPEN" for item in payload["campaigns"]) == 6
        assert [window["key"] for window in payload["performance_windows"]] == [
            "month",
            "quarter",
            "ytd",
            "r365",
        ]
        assert [series["key"] for series in payload["cash_chart_series"]] == [
            "month",
            "quarter",
            "ytd",
            "r365",
        ]
        assert [window["key"] for window in payload["cash_activity_windows"]] == [
            "month",
            "quarter",
            "ytd",
            "r365",
        ]
        assert len(payload["cash_events"]) == 25
        assert all(event["amount"] != "0" for event in payload["cash_events"])
        assert len(payload["cash_activity_windows"][0]["events"]) == 3
        assert all(
            event["amount"] != "0"
            for window in payload["cash_activity_windows"]
            for event in window["events"]
        )
        assert len(payload["expiration_calendar"]) == 5
        assert payload["expiration_calendar"][0]["days_to_expiration"] == 7
        assert len(payload["policies"]) == 3
        assert [
            (alert["symbol"], alert["reason_code"], alert["level"]) for alert in payload["alerts"]
        ] == [("CVX", "call_expiration_proximity", "watch")]
        assert payload["monthly_performance"][-1]["option_cash"] == "-930"
        assert payload["strategy_attribution"][0]["status"] == "CURRENT-INVENTORY PROXY"
        assert payload["strategy_attribution"][-1]["actual_result"] is None
        assert payload["operator_metrics"]["completed_months"] == 7
        assert payload["operator_metrics"]["median_completed_month"] == "2395"
        assert "objective" not in payload
        assert "monthly_target" not in payload["income"]
        price_events = [
            event for underlying in payload["underlyings"] for event in underlying["price_events"]
        ]
        assert sum(event["underlying_at_resolution"] is not None for event in price_events) == 22
        assert all(
            event["underlying_at_resolution"] is None
            for event in price_events
            if event["outcome"] == "Open"
        )

        assert page.status_code == 200
        assert "Incoooming" in page.text
        assert "Incoom &amp; Pacing" in page.text
        assert "Live options" in page.text
        assert 'data-period="week"' not in page.text
        assert 'data-period="month"' in page.text
        assert 'data-period="quarter"' in page.text
        assert 'data-period="ytd"' in page.text
        assert 'data-period="r365"' in page.text
        assert "Cash &amp; recent moves" in page.text
        assert "Cash timeline" not in page.text
        assert "EXECUTED CLOSE / ROLL DEBITS" in page.text
        assert "Transaction records" not in page.text
        assert "Open options" in page.text
        assert "Results" in page.text
        assert "2,000</b> SHARES" in page.text
        assert page.text.count("data-campaign-chart data-symbol") == 3
        assert page.text.count("data-campaign-chart-fallback") == 3
        assert page.text.count("data-campaign-chart-legacy") == 0
        assert page.text.count("data-cash-activity-window") == 4
        assert page.text.count("data-cash-event-target") == len(payload["recent_option_activity"])
        assert page.text.count("data-workspace-splitter") == 3
        assert page.text.count("data-nibwick-note\n      data-alert-id") == 1
        assert page.text.count("data-nibwick-note-jump") == 1
        assert "data-nibwick-active-count" in page.text
        assert "1 ACTIVE" in page.text
        assert "MONTHLY OPTION INCOME TARGET" not in page.text
    finally:
        container.close()


async def _request_initial_routes(container: Container) -> tuple[httpx.Response, ...]:
    transport = httpx.ASGITransport(app=create_app(container))
    source = "demo" if container.settings.demo_mode else "schwab"
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://test",
        cookies={"incoooming_source": source},
    ) as client:
        return (
            await client.get("/api/v1/health/live"),
            await client.get("/api/v1/health/ready"),
            await client.get("/api/v1/dashboard"),
            await client.get("/api/v1/sync/status"),
            await client.get("/"),
        )
