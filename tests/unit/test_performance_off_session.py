from __future__ import annotations

from copy import deepcopy
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest

from schwab_dashboard.application.performance.projection import build_performance_comparison

D = Decimal
THURSDAY = date(2026, 9, 10)
FRIDAY = date(2026, 9, 18)
SUNDAY = date(2026, 9, 20)
SESSIONS = (10, 11, 14, 15, 16, 17, 18)


def reconnect_history(*, weekend_cash: str = "0") -> dict[str, Any]:
    start = datetime(2026, 9, 10, 21, tzinfo=UTC)
    # Monday UTC is still Sunday in the market timezone.
    end = datetime(2026, 9, 21, 2, tzinfo=UTC)
    balances = tuple(
        {
            "account_id": "fixture-account",
            "sync_run_id": run,
            "observed_at": stamp,
            "liquidation_value": value,
            "maintenance_requirement": D("1000"),
        }
        for run, stamp, value in (
            ("before-outage", start, D("15000")),
            ("sunday-reconnect", end, D("15600") + D(weekend_cash)),
        )
    )
    positions = tuple(
        {
            "account_id": "fixture-account",
            "sync_run_id": row["sync_run_id"],
            "observed_at": row["observed_at"],
            "symbol": "TESTETF",
            "asset_type": "ETF",
            "net_quantity": D("100"),
            "market_value": value,
        }
        for row, value in zip(balances, (D("10000"), D("10600")), strict=True)
    )
    bars = tuple(
        {"symbol": symbol, "trade_date": date(2026, 9, day), "close": D(100 + i)}
        for symbol in ("TESTETF", "SPY")
        for i, day in enumerate(SESSIONS)
    )
    cash = (
        (
            {
                "account_id": "fixture-account",
                "occurred_at": datetime(2026, 9, 20, 14, tzinfo=UTC),
                "movement_type": "transfer",
                "amount": D(weekend_cash),
            },
        )
        if D(weekend_cash)
        else ()
    )
    return {
        "balance_history": balances,
        "position_history": positions,
        "daily_bars": bars,
        "cash_movements": cash,
    }


def test_sunday_reconnect_restores_gap_and_keeps_real_observation_date() -> None:
    history = reconnect_history()
    original = deepcopy(history)
    result = build_performance_comparison(**history)

    assert history == original
    assert result.coverage_end == SUNDAY
    assert [point.date for point in result.actual.points] == [
        *(date(2026, 9, day) for day in SESSIONS),
        SUNDAY,
    ]
    latest = result.actual.points[-1]
    assert latest.value == D("15600")
    assert latest.value_quality == "observed"
    assert latest.valuation_phase == "off_session"
    assert latest.return_quality == "provisional"
    assert latest.daily_return_percent is None
    assert latest.cumulative_return_percent == pytest.approx(D("4"))
    for point in result.actual.points[1:-1]:
        assert point.value_quality in {"derived", "estimated"}
        assert point.anchor_start == THURSDAY
        assert point.anchor_end == SUNDAY
    for series in (
        result.shares_without_options,
        result.market_reference,
        result.levered_market_reference,
    ):
        assert series.points[-1].date == FRIDAY
        assert SUNDAY not in {point.date for point in series.points}
    assert result.matched.as_of == FRIDAY
    assert result.spine.risk.observations == 0
    assert result.spine.capital_efficiency.observed_sessions == 1
    assert result.spine.capital_efficiency.latest_net_liquidation == latest.value
    assert any("market was closed" in warning for warning in result.warnings)


@pytest.mark.parametrize("cash", ["2500", "-2500"])
def test_weekend_owner_cash_is_removed_without_becoming_friday_performance(cash: str) -> None:
    result = build_performance_comparison(**reconnect_history(weekend_cash=cash))

    friday, sunday = result.actual.points[-2:]
    assert friday.date == FRIDAY and friday.external_flow == 0
    assert friday.value == D("15600")
    assert sunday.external_flow == D(cash)
    assert sunday.value == D("15600") + D(cash)
    assert sunday.cumulative_return_percent == pytest.approx(D("4"))
    assert sunday.daily_return_percent is None
    assert result.external_flows_excluded == D(cash)


def test_weekend_bridge_does_not_add_a_seventh_return_day() -> None:
    history = reconnect_history(weekend_cash="1000")
    # An unsupported position prevents precise replay: only a labeled bridge
    # between the original broker values is permitted.
    history["position_history"][0]["asset_type"] = "unknown"
    history["balance_history"][-1]["liquidation_value"] = D("17000")
    result = build_performance_comparison(**history)

    for point in result.actual.points[1:-1]:
        assert point.valuation_subtype == "endpoint_bridge"
        assert point.value_quality == "estimated"
    friday, sunday = result.actual.points[-2:]
    assert abs(friday.value - D("16000")) < D("0.000001")
    assert abs(sunday.interval_return_percent or D("0")) < D("0.000001")
    assert sunday.external_flow == D("1000")
    assert sunday.daily_return_percent is None


def test_a_later_session_replaces_intermediate_weekend_endpoint() -> None:
    history = reconnect_history()
    latest = dict(history["balance_history"][-1])
    latest.update(
        sync_run_id="monday",
        observed_at=datetime(2026, 9, 21, 21, tzinfo=UTC),
        liquidation_value=D("15700"),
    )
    history["balance_history"] += (latest,)
    position = dict(history["position_history"][-1])
    position.update(
        sync_run_id="monday",
        observed_at=latest["observed_at"],
        market_value=D("10700"),
    )
    history["position_history"] += (position,)
    history["daily_bars"] += tuple(
        {"symbol": symbol, "trade_date": date(2026, 9, 21), "close": D("107")}
        for symbol in ("TESTETF", "SPY")
    )
    result = build_performance_comparison(**history)

    assert SUNDAY not in {point.date for point in result.actual.points}
    assert result.actual.points[-1].valuation_phase == "close"
    assert result.coverage_end == date(2026, 9, 21)
    assert result.matched.as_of == date(2026, 9, 21)


@pytest.mark.parametrize("use_run_ids", [True, False])
def test_weekend_uses_latest_cohort_without_chaining_saturday(use_run_ids: bool) -> None:
    history = reconnect_history()
    saturday = dict(history["balance_history"][-1])
    saturday.update(
        sync_run_id="saturday",
        observed_at=datetime(2026, 9, 19, 21, tzinfo=UTC),
        liquidation_value=D("999999"),
    )
    history["balance_history"] += (saturday,)
    if not use_run_ids:
        for row in (*history["balance_history"], *history["position_history"]):
            row.pop("sync_run_id", None)
    result = build_performance_comparison(**history)

    assert date(2026, 9, 19) not in {point.date for point in result.actual.points}
    assert result.actual.points[-1].value == D("15600")


def test_holiday_reconnect_is_current_without_creating_holiday_closes() -> None:
    history = reconnect_history()
    for rows in (history["balance_history"], history["position_history"]):
        rows[0]["observed_at"] = datetime(2026, 9, 3, 21, tzinfo=UTC)
        rows[-1]["observed_at"] = datetime(2026, 9, 7, 21, tzinfo=UTC)
    history["daily_bars"] = tuple(
        {"symbol": symbol, "trade_date": date(2026, 9, day), "close": D(price)}
        for symbol in ("TESTETF", "SPY")
        for day, price in ((3, "100"), (4, "106"))
    )
    result = build_performance_comparison(**history)

    assert result.coverage_end == date(2026, 9, 7)
    assert result.actual.points[-1].valuation_phase == "off_session"
    assert result.actual.points[-1].daily_return_percent is None
    assert result.matched.as_of == date(2026, 9, 4)


def test_weekend_account_coverage_change_keeps_return_unresolved() -> None:
    history = reconnect_history()
    extra = dict(
        history["balance_history"][-1], account_id="new-account", liquidation_value=D("5000")
    )
    history["balance_history"] += (extra,)
    result = build_performance_comparison(**history)

    assert result.coverage_end == SUNDAY
    assert result.actual.points[-1].value == D("20600")
    assert result.actual.points[-1].cumulative_return_percent is None
    assert result.actual.points[-1].quality == "account_coverage_changed"
    assert result.actual.points[-1].daily_return_percent is None
