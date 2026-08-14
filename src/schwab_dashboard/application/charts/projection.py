from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from schwab_dashboard.application.charts.models import (
    CampaignChart,
    ChartAudit,
    ChartBar,
    ChartCampaign,
    ChartInterval,
    ChartLeg,
    ChartShareEvent,
)
from schwab_dashboard.application.dashboard.covered_calls import UnderlyingCallStats


def build_campaign_chart(
    underlying: UnderlyingCallStats,
    *,
    daily_bars: Sequence[Mapping[str, object]] = (),
    intraday_bars: Sequence[Mapping[str, object]] = (),
) -> CampaignChart:
    """Project the reconciled option ledger into one broker-neutral chart contract.

    The browser does no lifecycle inference. Campaign identity, quantity-aware leg
    order, state, and net cash all arrive from the backend projection.
    """

    grouped: dict[str, list[ChartLeg]] = defaultdict(list)
    for event in sorted(
        underlying.price_events,
        key=lambda item: (item.date, item.campaign_id, item.campaign_leg_index, item.sequence),
    ):
        grouped[event.campaign_id].append(
            ChartLeg(
                id=event.record_id,
                sequence=event.sequence,
                campaign_id=event.campaign_id,
                campaign_label=event.campaign_label,
                leg_index=event.campaign_leg_index,
                time=event.date,
                underlying_price=event.price,
                event_type=event.event_type,
                outcome=event.outcome,
                option_side=event.option_side,
                strike=event.strike,
                expiration=event.expires_on,
                contracts=event.contracts,
                net_cash=event.net_cash,
                campaign_net_cash=event.campaign_net_cash,
                detail=event.detail,
                confidence=event.campaign_confidence,
                is_open=event.outcome.upper() == "OPEN",
            )
        )

    campaigns = tuple(
        _campaign(campaign_id, legs)
        for campaign_id, legs in sorted(
            grouped.items(),
            key=lambda item: (item[1][0].time, item[1][0].campaign_label, item[0]),
        )
    )
    confidence = Counter(item.confidence for item in campaigns)
    unknown = confidence["unknown"]
    needs_review = sum(_campaign_needs_review(item) for item in campaigns)
    bars = _chart_bars(underlying.symbol, daily_bars)
    if not bars:
        bars = tuple(
            ChartBar(
                time=item.date,
                value=item.price,
                open=item.price,
                high=item.price,
                low=item.price,
                close=item.price,
            )
            for item in underlying.price_points
        )
    intervals = _chart_intervals(underlying.symbol, bars, intraday_bars)
    return CampaignChart(
        version="campaign-chart-v4",
        symbol=underlying.symbol,
        as_of=bars[-1].time,
        bars=bars,
        intervals=intervals,
        default_interval="1d",
        campaigns=campaigns,
        share_events=tuple(
            ChartShareEvent(
                time=item.date,
                action=item.action,
                shares=item.shares,
                price=item.price,
                detail=(
                    f"{item.gross_buys} bought / {item.gross_sells} sold"
                    if item.gross_buys and item.gross_sells
                    else f"{item.shares} shares {item.action}"
                ),
            )
            for item in underlying.share_trade_events
        ),
        audit=ChartAudit(
            campaigns=len(campaigns),
            events=sum(len(item.legs) for item in campaigns),
            exact_campaigns=confidence["exact"],
            inferred_campaigns=confidence["inferred"],
            unknown_campaigns=unknown,
            needs_review_campaigns=needs_review,
            removal_gate_passed=bool(campaigns) and unknown == 0 and needs_review == 0,
        ),
    )


def _campaign(campaign_id: str, legs: list[ChartLeg]) -> ChartCampaign:
    ordered = tuple(sorted(legs, key=lambda item: (item.time, item.sequence, item.leg_index)))
    latest = ordered[-1]
    # Opening sales remain part of the lifecycle after a campaign resolves.
    # Only the latest reconciled leg owns the campaign's current state.
    is_open = latest.is_open
    return ChartCampaign(
        id=campaign_id,
        label=ordered[0].campaign_label,
        option_side=ordered[0].option_side,
        status="OPEN" if is_open else latest.outcome.upper(),
        confidence=_lowest_confidence(item.confidence for item in ordered),
        opened_on=ordered[0].time,
        latest_on=latest.time,
        # The lifecycle reconciler owns campaign cash. Do not re-derive it from
        # display legs: assignments, partial closes, and multi-event rolls can
        # otherwise be counted twice by a presentation projection.
        net_cash=latest.campaign_net_cash,
        legs=ordered,
    )


def _lowest_confidence(values: Iterable[str]) -> str:
    rank = {"exact": 0, "user_confirmed": 1, "inferred": 2, "unknown": 3}
    normalized = tuple(str(item) for item in values)
    return max(normalized, key=lambda item: rank.get(item, 3), default="unknown")


def _campaign_needs_review(campaign: ChartCampaign) -> int:
    labels = {item.campaign_label for item in campaign.legs}
    indexes = [item.leg_index for item in campaign.legs]
    chronological = indexes == sorted(indexes)
    return int(len(labels) > 1 or not chronological)


def _chart_bars(
    symbol: str | None,
    rows: Sequence[Mapping[str, object]],
) -> tuple[ChartBar, ...]:
    if not symbol:
        return ()
    normalized = symbol.upper()
    selected = sorted(
        (row for row in rows if str(row.get("symbol") or "").upper() == normalized),
        key=lambda row: _date(row.get("trade_date")),
    )
    return tuple(
        ChartBar(
            time=_date(row.get("trade_date")),
            value=_decimal(row.get("close")),
            open=_decimal(row.get("open")),
            high=_decimal(row.get("high")),
            low=_decimal(row.get("low")),
            close=_decimal(row.get("close")),
            volume=int(str(row.get("volume") or 0)),
        )
        for row in selected
    )


def _chart_intervals(
    symbol: str,
    daily: tuple[ChartBar, ...],
    rows: Sequence[Mapping[str, object]],
) -> tuple[ChartInterval, ...]:
    raw = _intraday_rows(symbol, rows)
    intervals: list[ChartInterval] = []
    for key, label, minutes in (("1h", "1H", 60), ("4h", "4H", 240)):
        aggregated = _aggregate_intraday(raw, minutes)
        if aggregated:
            intervals.append(
                ChartInterval(
                    key=key,
                    label=label,
                    minutes=minutes,
                    bars=aggregated,
                    extended_hours=True,
                )
            )
    intervals.append(
        ChartInterval(
            key="1d",
            label="1D",
            minutes=1440,
            bars=daily,
            extended_hours=False,
        )
    )
    return tuple(intervals)


def _intraday_rows(
    symbol: str,
    rows: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    normalized = symbol.upper()
    selected = (
        row for row in rows if str(row.get("symbol") or "").upper() == normalized
    )
    return tuple(
        {
            "started_at": _datetime(row.get("started_at")),
            "open": _decimal(row.get("open")),
            "high": _decimal(row.get("high")),
            "low": _decimal(row.get("low")),
            "close": _decimal(row.get("close")),
            "volume": int(str(row.get("volume") or 0)),
        }
        for row in sorted(selected, key=lambda item: _datetime(item.get("started_at")))
    )


def _aggregate_intraday(
    rows: tuple[dict[str, object], ...],
    minutes: int,
) -> tuple[ChartBar, ...]:
    if not rows:
        return ()
    eastern = ZoneInfo("America/New_York")
    grouped: dict[tuple[date, int], list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        started_at = _datetime(row["started_at"])
        local = started_at.astimezone(eastern)
        minute_of_day = local.hour * 60 + local.minute
        # Anchor buckets to the 04:00 ET extended-hours session. Bars outside
        # that window remain ordered in deterministic pre/post-session buckets.
        bucket = (minute_of_day - 240) // minutes
        grouped[(local.date(), bucket)].append(row)
    bars: list[ChartBar] = []
    for rows_in_bucket in grouped.values():
        ordered = sorted(rows_in_bucket, key=lambda item: _datetime(item["started_at"]))
        bars.append(
            ChartBar(
                time=_datetime(ordered[0]["started_at"]),
                value=_decimal(ordered[-1]["close"]),
                open=_decimal(ordered[0]["open"]),
                high=max(_decimal(item["high"]) for item in ordered),
                low=min(_decimal(item["low"]) for item in ordered),
                close=_decimal(ordered[-1]["close"]),
                volume=sum(int(str(item["volume"])) for item in ordered),
            )
        )
    return tuple(sorted(bars, key=lambda item: _datetime(item.time)))


def _date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=ZoneInfo("UTC"))
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=ZoneInfo("UTC"))


def _decimal(value: object) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value or 0))
