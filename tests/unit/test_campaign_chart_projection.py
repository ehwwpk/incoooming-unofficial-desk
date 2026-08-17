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

    assert chart.version == "campaign-chart-v5"
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


def test_campaign_chart_preserves_verified_execution_time_without_inventing_csv_time() -> None:
    snapshot = DemoDashboardReader().execute()
    underlying = snapshot.underlyings[0]
    exact_at = datetime(2026, 8, 12, 14, 37, tzinfo=UTC)
    exact = replace(
        underlying.price_events[0],
        date=exact_at.date(),
        occurred_at=exact_at,
        time_precision="exact",
    )
    date_only = replace(
        underlying.price_events[1],
        occurred_at=None,
        time_precision="date_only",
    )
    changed = replace(
        underlying,
        price_events=(exact, date_only, *underlying.price_events[2:]),
    )

    chart = build_campaign_chart(changed)
    legs = {
        leg.sequence: leg for campaign in chart.campaigns for leg in campaign.legs
    }

    assert legs[exact.sequence].time == exact_at
    assert legs[exact.sequence].time_precision == "exact"
    assert legs[date_only.sequence].time == date_only.date
    assert legs[date_only.sequence].time_precision == "date_only"


def test_open_campaigns_receive_sourced_risk_reference_only_while_open() -> None:
    snapshot = DemoDashboardReader().execute()
    underlying = snapshot.underlyings[0]

    chart = build_campaign_chart(underlying)
    open_with_reference = [
        campaign
        for campaign in chart.campaigns
        if campaign.status == "OPEN" and campaign.risk_reference is not None
    ]

    assert open_with_reference
    assert all(
        item.risk_reference.source in {"SCHWAB OPTION IV", "STRIKE / SPOT ONLY"}
        for item in open_with_reference
    )
    assert all(
        campaign.risk_reference is None for campaign in chart.campaigns if campaign.status != "OPEN"
    )


def test_open_campaigns_fall_back_to_strike_and_spot_without_inventing_iv() -> None:
    snapshot = DemoDashboardReader().execute()
    underlying = replace(snapshot.underlyings[0], open_call_clocks=())

    chart = build_campaign_chart(underlying)
    open_campaigns = [campaign for campaign in chart.campaigns if campaign.status == "OPEN"]

    assert open_campaigns
    assert all(campaign.risk_reference is not None for campaign in open_campaigns)
    assert all(
        campaign.risk_reference.source == "STRIKE / SPOT ONLY"
        and campaign.risk_reference.expected_move is None
        and campaign.risk_reference.implied_volatility_percent is None
        for campaign in open_campaigns
        if campaign.risk_reference is not None
    )


def _events_by_campaign(events: Sequence[PriceEvent]) -> dict[str, list[PriceEvent]]:
    grouped: dict[str, list[PriceEvent]] = {}
    for event in events:
        grouped.setdefault(event.campaign_id, []).append(event)
    return grouped
