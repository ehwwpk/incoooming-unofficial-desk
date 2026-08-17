from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime

from schwab_dashboard.application.charts import build_campaign_chart
from schwab_dashboard.application.charts.models import CampaignChart
from schwab_dashboard.application.dashboard.calculations import map_positions
from schwab_dashboard.application.dashboard.live_positions import build_live_position_book
from schwab_dashboard.application.dashboard.live_underlying_stats import (
    build_live_underlying_stats,
)
from schwab_dashboard.application.market_time import market_date
from schwab_dashboard.application.ports.analytics import LiveAnalyticsReader
from schwab_dashboard.application.ports.dashboard import DashboardReader
from schwab_dashboard.application.ports.repositories import UnitOfWorkFactory


class ReadLiveCampaignChart:
    """Read one symbol's chart without constructing the portfolio dashboard."""

    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        analytics_reader: LiveAnalyticsReader,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._analytics_reader = analytics_reader
        self._clock = clock or _utc_now

    def execute(self, symbol: str) -> CampaignChart:
        normalized = symbol.strip().upper()
        if not normalized:
            raise LookupError("Give the chart a ticker symbol.")
        with self._uow_factory() as uow:
            latest_sync = uow.sync_runs.latest_successful(source="schwab_full")
            if latest_sync is None:
                latest_sync = uow.sync_runs.latest_successful(source="schwab")
            positions = tuple(
                position
                for position in map_positions(uow.positions.list_latest())
                if _position_matches(position.symbol, position.underlying_symbol, normalized)
            )
        if not positions:
            raise LookupError(f"No live position history is available for {normalized}.")

        option_symbols = tuple(
            position.symbol for position in positions if position.asset_type.upper() == "OPTION"
        )
        option_market = self._analytics_reader.list_latest_option_market(symbols=option_symbols)
        underlying_market = self._analytics_reader.list_latest_underlying_market(
            symbols=(normalized,)
        )
        executions = _matching_rows(self._analytics_reader.list_executions(), normalized)
        cash_movements = _matching_rows(self._analytics_reader.list_cash_movements(), normalized)
        lifecycle_events = _matching_rows(
            self._analytics_reader.list_lifecycle_events(), normalized
        )
        daily_bars = self._analytics_reader.list_daily_bars(symbols=(normalized,))
        intraday_bars = self._analytics_reader.list_intraday_bars(symbols=(normalized,))
        evaluated_at = self._clock()
        as_of = market_date(
            latest_sync.completed_at
            if latest_sync is not None and latest_sync.completed_at is not None
            else evaluated_at
        )
        live_book = build_live_position_book(
            positions,
            as_of=as_of,
            evaluated_at=evaluated_at,
            option_market=option_market,
            underlying_market=underlying_market,
            daily_bars=daily_bars,
            executions=executions,
        )
        underlyings = build_live_underlying_stats(
            live_book=live_book,
            positions=positions,
            executions=executions,
            cash_movements=cash_movements,
            lifecycle_events=lifecycle_events,
            daily_bars=daily_bars,
            option_market=option_market,
            as_of=as_of,
        )
        underlying = next(
            (item for item in underlyings if item.symbol.upper() == normalized),
            None,
        )
        if underlying is None:
            raise LookupError(f"No chart history is available for {normalized}.")
        return build_campaign_chart(
            underlying,
            daily_bars=daily_bars,
            intraday_bars=intraday_bars,
        )


class ReadSnapshotCampaignChart:
    """Project a demo or imported dashboard without broker-specific assumptions."""

    def __init__(self, dashboard: DashboardReader) -> None:
        self._dashboard = dashboard

    def execute(self, symbol: str) -> CampaignChart:
        normalized = symbol.strip().upper()
        snapshot = self._dashboard.execute()
        underlying = next(
            (item for item in snapshot.underlyings if item.symbol.upper() == normalized),
            None,
        )
        if underlying is None:
            raise LookupError(f"No chart history is available for {normalized}.")
        return build_campaign_chart(underlying)


def _position_matches(symbol: str, underlying_symbol: str | None, requested: str) -> bool:
    return symbol.upper() == requested or (underlying_symbol or "").upper() == requested


def _matching_rows(
    rows: Sequence[Mapping[str, object]], symbol: str
) -> tuple[Mapping[str, object], ...]:
    return tuple(
        row
        for row in rows
        if str(row.get("underlying_symbol") or row.get("symbol") or "").upper() == symbol
    )


def _utc_now() -> datetime:
    return datetime.now(UTC)
