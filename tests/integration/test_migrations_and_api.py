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
            "underlying_market_snapshots",
            "workspace_preferences",
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
        assert "Incoooming Unofficial Desk" in page.text
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
        assert [
            (alert["reason_code"], alert["level"], alert["symbol"]) for alert in payload["alerts"]
        ] == [
            ("fast_move_near_call", "check", "KTOS"),
            ("dividend_overlap", "watch", "CVX"),
        ]
        assert payload["alerts"][0]["roll_scenarios"][0]["target_strike"] == "70"
        assert payload["alerts"][0]["roll_scenarios"][0]["net_roll_cash"] == "25.00"
        assert payload["alerts"][0]["roll_scenarios"][1]["added_days"] == 42
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
        assert "SIMULATION" in page.text
        assert '<span class="brand-mark">IU</span>' in page.text
        assert "Income &amp; pace" in page.text
        assert "Live covered calls" in page.text
        assert "What is open right now" not in page.text
        assert "WINDOW ACCOUNTING" not in page.text
        assert "TRANSACTION CASH · NORMALIZED PACE · OPEN MARK SEPARATED" not in page.text
        assert "INTERNAL DESK FEED" not in page.text
        assert "NO MARKET HEADLINES" not in page.text
        assert "R365" in page.text
        assert "MONTHLY OPTION INCOME TARGET" in page.text
        assert 'data-period="month"' in page.text
        assert 'aria-label="Four weeks" aria-selected="true"' in page.text
        assert 'data-period-sheet="month"' in page.text
        assert "data-target-input" in page.text
        assert "DIV RISK // MONITOR" not in page.text
        assert "WORTH CHECKING" in page.text
        assert "KEEP AN EYE ON THIS" in page.text
        assert "Fast move; $65 call is 7.0% away" in page.text
        assert "CVX&#39;s dividend needs context" in page.text
        assert "55/100 ELEVATED" in page.text
        assert "$231.78" in page.text
        assert "nibwick-method-note" in page.text
        assert "CHECK SOON" not in page.text
        assert "app.css?v=43" in page.text
        assert "DEMO CHECKED" in page.text
        assert "$4.23 / 7.0% TO STRIKE" in page.text
        assert "periods.js?v=16" in page.text
        assert "workspace-splitter.js?v=1" in page.text
        assert "chart-viewport.js?v=1" in page.text
        assert "chart-focus.js?v=1" in page.text
        assert "event-layout.js?v=4" in page.text
        assert "lifecycle-links.js?v=2" in page.text
        assert "nibwick-alerts.js?v=8" in page.text
        assert "nibwick.js?v=5" in page.text
        assert "position-details.js?v=1" in page.text
        assert page.text.count("data-position-details") == 3
        assert page.text.count('class="position-detail"') == 3
        assert page.text.count("data-chart-range=") == 9
        assert page.text.count("data-chart-focus") == 3
        assert page.text.count("data-chart-point") == 174
        assert page.text.count("data-chart-event data-date") == 31
        assert page.text.count("data-nibwick-note ") == 2
        assert "data-nibwick-alert-badge" in page.text
        assert "nibwick-alert-plaque" in page.text
        assert "nibwick-portrait-art" not in page.text
        assert 'data-nibwick-popover role="dialog"' in page.text
        assert "data-nibwick-panel-title" in page.text
        assert "data-nibwick-scene" in page.text
        assert "nibwick-note-heading" in page.text
        assert "data-nibwick-unread-count" in page.text
        assert 'data-alert-id="ktos-fast-move"' in page.text
        assert "METHOD / LIMITS" in page.text
        assert page.text.count("()___()") >= 5
        assert 'data-alert-target="ktos-workspace"' in page.text
        assert "[GO]</span> KTOS" in page.text
        assert 'aria-labelledby="nibwick-panel-title" hidden' in page.text
        assert "data-nibwick-announcement" in page.text
        assert "data-nibwick-wire" not in page.text
        assert page.text.count("data-workspace-splitter") == 3
        assert page.text.count("data-event-leaders") == 3
        assert page.text.count("data-lifecycle-id=") == 27
        assert page.text.count("data-linked-sale-sequence=") == 11
        assert page.text.count("data-share-trade=") == 4
        assert 'class="nibwick-obstacle"' in page.text
        assert "resolves sale event 1" in page.text
        assert "Open Nibwick's notes" in page.text
        assert 'role="separator"' in page.text
        assert 'class="underlying-history"' in page.text
        assert 'data-rail-link="portfolio" aria-current="page"' in page.text
        assert "NET OPTION INCOME / 4 WEEKS" in page.text
        assert "EXECUTED CLOSE / ROLL DEBITS" not in page.text
        assert "OPEN-CALL CREDIT RECEIVED" not in page.text
        assert "CURRENT OPEN-CALL VALUE" not in page.text
        assert "OPEN BOOK · NOT WINDOW CASH" not in page.text
        assert 'data-monthly-option-average="$2,648.33"' in page.text
        assert 'data-monthly-total-average="$3,084.67"' in page.text
        assert "data-active-option-average hidden" in page.text
        assert "PREMIUM RECEIVED / CURRENT MARK / OPEN P&amp;L" in page.text
        assert "PORTFOLIO OPEN-CALL DECAY EST. / DAY" not in page.text
        assert "OPEN MARK P/L" in page.text
        assert "OPEN P/L AT CURRENT MARK" in page.text
        assert "OPTION VALUE NOW" in page.text
        assert "FULL DAILY CLOSES" in page.text
        assert "58 MARKET SESSIONS" in page.text
        assert "YAHOO FINANCE CLOSE" in page.text
        assert 'data-buyback-drag="34.1%"' in page.text
        assert "42.5% executed-debit drag" not in page.text
        assert "TIME ELAPSED" in page.text
        assert "RANGE POSITION" in page.text
        assert "LIFETIME BASIS LENS" not in page.text
        assert "ORIGINAL CAPITAL REMAINING" not in page.text
        assert "13-week cash trend" in page.text
        assert "AGGREGATED WEEKLY OPTION AND DIVIDEND TOTALS" in page.text
        assert "Transaction records" in page.text
        assert "NEAR-FLAT ROLL CHECKS" in page.text
        assert "BTC ASK + STO BID · SIMULATED CHAIN" in page.text
        assert "+$25 total · $2,500 more call-away room" in page.text
        assert "data-nibwick-summary-count" in page.text
        assert "data-nibwick-summary-detail" in page.text
        assert "Covered-call activity" in page.text
        assert "TRADE-BY-TRADE" in page.text
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
