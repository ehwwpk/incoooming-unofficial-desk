from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from schwab_dashboard.application.dashboard.models import PositionSummary
from schwab_dashboard.application.market_time import market_date
from schwab_dashboard.application.performance.flows import (
    carried_external_flow,
    external_flow_on,
    movement_timestamp,
)

D = Decimal


def _position(**overrides: object) -> PositionSummary:
    values: dict[str, object] = {
        "account_mask": "...1234",
        "symbol": "KTOS",
        "description": "Kratos Defense",
        "asset_type": "EQUITY",
        "quantity": D("800"),
        "average_price": D("40"),
        "mark": D("60"),
        "market_value": D("48000"),
        "day_profit_loss": D("-219.03"),
        "day_profit_loss_percent": D("-0.4"),
        "strategy": None,
    }
    values.update(overrides)
    return PositionSummary(**values)  # type: ignore[arg-type]


def test_external_flow_uses_new_york_market_day_not_utc_date() -> None:
    movements = (
        {
            "occurred_at": datetime(2026, 8, 12, 18, 8, 21),
            "movement_type": "transfer",
            "amount": D("25000"),
        },
    )

    assert external_flow_on(movements, date(2026, 8, 12)) == D("25000")
    assert external_flow_on(movements, date(2026, 8, 13)) == D("0")


def test_carried_external_flow_while_schwab_baseline_is_stale() -> None:
    positions = (_position(),)
    movements = (
        {
            "occurred_at": datetime(2026, 8, 12, 18, 8, 21),
            "movement_type": "transfer",
            "amount": D("25000"),
        },
    )
    account_day_change = D("131586.73") - D("106805.76")

    assert carried_external_flow(
        movements,
        as_of=date(2026, 8, 13),
        account_day_change=account_day_change,
        positions=positions,
    ) == D("25000")


def test_carried_external_flow_stops_after_schwab_baseline_advances() -> None:
    positions = (_position(),)
    movements = (
        {
            "occurred_at": datetime(2026, 8, 12, 18, 8, 21),
            "movement_type": "transfer",
            "amount": D("25000"),
        },
    )
    account_day_change = D("131586.73") - D("131805.76")

    assert carried_external_flow(
        movements,
        as_of=date(2026, 8, 13),
        account_day_change=account_day_change,
        positions=positions,
    ) == D("0")


def test_external_flow_counts_naive_utc_afternoon_on_the_new_york_date() -> None:
    movements = (
        {
            "occurred_at": datetime(2026, 8, 12, 18, 8, 21),
            "movement_type": "transfer",
            "amount": D("25000"),
        },
    )
    as_of = datetime(2026, 8, 13, 2, 0, tzinfo=UTC)

    assert market_date(as_of) == date(2026, 8, 12)
    assert external_flow_on(movements, market_date(as_of)) == D("25000")


def test_date_only_activity_restored_from_sqlite_stays_on_broker_date() -> None:
    stored = datetime(2026, 8, 12)
    movements = (
        {
            "occurred_at": stored,
            "movement_type": "transfer",
            "amount": D("25000"),
        },
    )

    assert movement_timestamp(stored) == datetime(
        2026,
        8,
        12,
        tzinfo=ZoneInfo("America/New_York"),
    )
    assert external_flow_on(movements, date(2026, 8, 12)) == D("25000")
    assert external_flow_on(movements, date(2026, 8, 11)) == D("0")
