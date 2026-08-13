from datetime import date
from decimal import Decimal

from schwab_dashboard.application.dashboard.live_cash_series import (
    build_live_cash_chart_series,
)
from schwab_dashboard.application.dashboard.live_performance import (
    build_live_performance,
)
from schwab_dashboard.application.dashboard.live_positions import (
    build_live_position_book,
)
from schwab_dashboard.infrastructure.demo.dashboard import DemoDashboardReader

D = Decimal


def _execution(
    external_key: str,
    occurred_on: date,
    net_cash: str,
    *,
    side: str = "sell",
    position_effect: str = "opening",
) -> dict[str, object]:
    return {
        "external_key": external_key,
        "occurred_at": occurred_on,
        "asset_type": "option",
        "option_side": "call",
        "side": side,
        "position_effect": position_effect,
        "gross_amount": abs(D(net_cash)),
        "net_cash": D(net_cash),
        "quantity": 1,
        "underlying_symbol": "KTOS",
        "symbol": "KTOS",
        "fees": D("0"),
    }


def test_live_cash_series_reconciles_to_normalized_records() -> None:
    as_of = date(2026, 8, 11)
    executions = (
        _execution("open", date(2026, 8, 11), "300"),
        _execution(
            "close",
            date(2026, 8, 5),
            "-125",
            side="buy",
            position_effect="closing",
        ),
    )
    dividends = (
        {
            "external_key": "dividend",
            "occurred_at": date(2026, 8, 7),
            "movement_type": "dividend",
            "symbol": "CVX",
            "amount": D("42"),
        },
    )

    series = {
        item.key: item
        for item in build_live_cash_chart_series(
            executions=executions,
            dividends=dividends,
            as_of=as_of,
        )
    }

    assert tuple(series) == ("month", "quarter", "ytd", "r365")
    assert len(series["month"].points) == 28
    for item in series.values():
        assert sum((point.premium_received for point in item.points), D("0")) == D(
            "300"
        )
        assert sum((point.executed_debits for point in item.points), D("0")) == D(
            "125"
        )
        assert sum((point.option_cash for point in item.points), D("0")) == D(
            "175"
        )
        assert sum((point.dividends for point in item.points), D("0")) == D("42")


def test_live_months_begin_at_first_record_and_exclude_partial_edges_from_average() -> None:
    snapshot = DemoDashboardReader().execute()
    as_of = date(2026, 8, 11)
    projection = build_live_performance(
        executions=(
            _execution("june", date(2026, 6, 15), "100"),
            _execution("july", date(2026, 7, 15), "200"),
            _execution("august", date(2026, 8, 5), "300"),
        ),
        cash_movements=(),
        lifecycle_events=(),
        live_book=build_live_position_book(snapshot.positions, as_of=as_of),
        covered_capital=D("100000"),
        as_of=as_of,
    )

    assert [item.label for item in projection.monthly_performance] == [
        "Jun 26",
        "Jul 26",
        "Aug 26",
    ]
    assert projection.monthly_performance[0].coverage_status == "coverage_start"
    assert projection.monthly_performance[-1].is_partial
    assert projection.operator_metrics.completed_months == 1
    assert projection.operator_metrics.rolling_year_monthly_average == D("200")
    assert projection.operator_metrics.median_completed_month == D("200")
