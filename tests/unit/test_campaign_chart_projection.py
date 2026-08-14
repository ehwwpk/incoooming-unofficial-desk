from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

from schwab_dashboard.application.charts import build_campaign_chart
from schwab_dashboard.application.dashboard.covered_calls import PriceEvent
from schwab_dashboard.infrastructure.demo.dashboard import DemoDashboardReader


def test_campaign_chart_uses_one_reconciled_campaign_identity() -> None:
    snapshot = DemoDashboardReader().execute()
    underlying = snapshot.underlyings[0]

    chart = build_campaign_chart(underlying)

    assert chart.version == "campaign-chart-v4"
    assert chart.symbol == underlying.symbol
    assert len(chart.bars) == len(underlying.price_points)
    assert sum(len(item.legs) for item in chart.campaigns) == len(underlying.price_events)
    assert all(
        leg.campaign_id == campaign.id for campaign in chart.campaigns for leg in campaign.legs
    )
    assert all(
        [leg.sequence for leg in campaign.legs] == sorted(leg.sequence for leg in campaign.legs)
        for campaign in chart.campaigns
    )
    expected_cash = {
        campaign_id: events[-1].campaign_net_cash
        for campaign_id, events in _events_by_campaign(underlying.price_events).items()
    }
    assert {campaign.id: campaign.net_cash for campaign in chart.campaigns} == expected_cash
    assert all(
        campaign.status
        == ("OPEN" if campaign.legs[-1].is_open else campaign.legs[-1].outcome.upper())
        for campaign in chart.campaigns
    )


def test_campaign_chart_keeps_unknown_history_visible_and_flags_audit_uncertainty() -> None:
    snapshot = DemoDashboardReader().execute()
    underlying = snapshot.underlyings[0]
    event = replace(underlying.price_events[0], campaign_confidence="unknown")
    changed = replace(underlying, price_events=(event, *underlying.price_events[1:]))

    chart = build_campaign_chart(changed)

    assert chart.audit.unknown_campaigns >= 1
    assert chart.audit.removal_gate_passed is False
    assert any(leg.id == event.record_id for campaign in chart.campaigns for leg in campaign.legs)


def test_campaign_chart_prefers_ohlc_rows_and_projects_intraday_intervals() -> None:
    snapshot = DemoDashboardReader().execute()
    underlying = snapshot.underlyings[0]
    rows = (
        {
            "symbol": underlying.symbol,
            "trade_date": date(2026, 8, 12),
            "open": Decimal("100"),
            "high": Decimal("105"),
            "low": Decimal("98"),
            "close": Decimal("104"),
            "volume": 1234,
        },
    )
    intraday = (
        {
            "symbol": underlying.symbol,
            "started_at": datetime(2026, 8, 12, 13, 0, tzinfo=UTC),
            "interval_minutes": 30,
            "open": Decimal("100"),
            "high": Decimal("102"),
            "low": Decimal("99"),
            "close": Decimal("101"),
            "volume": 100,
        },
        {
            "symbol": underlying.symbol,
            "started_at": datetime(2026, 8, 12, 13, 30, tzinfo=UTC),
            "interval_minutes": 30,
            "open": Decimal("101"),
            "high": Decimal("105"),
            "low": Decimal("100"),
            "close": Decimal("104"),
            "volume": 200,
        },
    )

    chart = build_campaign_chart(
        underlying,
        daily_bars=rows,
        intraday_bars=intraday,
    )

    assert chart.bars[0].open == Decimal("100")
    assert chart.bars[0].close == Decimal("104")
    assert chart.bars[0].volume == 1234
    assert [item.key for item in chart.intervals] == ["1h", "4h", "1d"]
    hourly = chart.intervals[0]
    assert hourly.bars[0].open == Decimal("100")
    assert hourly.bars[0].close == Decimal("104")
    assert hourly.bars[0].volume == 300
    assert hourly.extended_hours is True


def _events_by_campaign(events: Sequence[PriceEvent]) -> dict[str, list[PriceEvent]]:
    grouped: dict[str, list[PriceEvent]] = {}
    for event in events:
        grouped.setdefault(event.campaign_id, []).append(event)
    return grouped
