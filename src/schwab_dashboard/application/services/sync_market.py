from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

import httpx

from schwab_dashboard.application.ports.repositories import UnitOfWorkFactory
from schwab_dashboard.application.services.market_history_refresh import (
    MarketHistoryRefreshPolicy,
)
from schwab_dashboard.application.services.record_market_observations import (
    RecordMarketObservations,
)
from schwab_dashboard.domain.instruments import AssetType
from schwab_dashboard.infrastructure.schwab.gateway import SchwabReadOnlyMarketDataClient
from schwab_dashboard.infrastructure.schwab.market_mapper import SchwabMarketMapper

MARKET_REFERENCE_SYMBOLS = frozenset({"SPY"})
INTRADAY_LOOKBACK = timedelta(days=60)
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MarketSyncResult:
    underlying_quote_count: int
    option_quote_count: int
    daily_bar_count: int
    completed_at: datetime
    intraday_bar_count: int = 0


class SyncSchwabMarketData:
    def __init__(
        self,
        *,
        client: SchwabReadOnlyMarketDataClient,
        mapper: SchwabMarketMapper,
        recorder: RecordMarketObservations,
        uow_factory: UnitOfWorkFactory,
        parser_version: str,
        history_refresh_policy: MarketHistoryRefreshPolicy | None = None,
    ) -> None:
        self._client = client
        self._mapper = mapper
        self._recorder = recorder
        self._uow_factory = uow_factory
        self._parser_version = parser_version
        self._history_refresh_policy = history_refresh_policy

    def execute(self) -> MarketSyncResult:
        with self._uow_factory() as uow:
            positions = tuple(uow.positions.list_latest())

        held_assets = _held_market_assets(positions)
        symbols = sorted(held_assets)
        option_positions: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
        for row in positions:
            if str(row.get("asset_type") or "").upper() != "OPTION":
                continue
            if not row.get("short_quantity"):
                continue
            underlying = row.get("underlying_symbol")
            expiration = row.get("expiration_date")
            if underlying and expiration:
                option_positions[str(underlying)].append(dict(row))

        underlying_count = 0
        option_count = 0
        daily_bar_count = 0
        intraday_bar_count = 0
        if symbols:
            quotes = self._client.get_quotes(symbols)
            quote_received_at = datetime.now(UTC)
            quote_result = self._recorder.execute(
                self._mapper.map_quotes(
                    quotes,
                    observed_at=quote_received_at,
                    parser_version=self._parser_version,
                )
            )
            underlying_count += quote_result.underlying_snapshot_count

        for underlying, rows in sorted(option_positions.items()):
            expirations = [_as_date(row["expiration_date"]) for row in rows]
            chain = self._client.get_option_chain(
                underlying,
                from_date=min(expirations),
                to_date=max(expirations) + timedelta(days=56),
                contract_type="ALL",
            )
            chain_received_at = datetime.now(UTC)
            chain_result = self._recorder.execute(
                self._mapper.map_chain(
                    chain,
                    observed_at=chain_received_at,
                    parser_version=self._parser_version,
                )
            )
            option_count += chain_result.option_snapshot_count

        # Daily history is a portfolio input, not merely an option-chain input.
        # Store it for every held market symbol so the frozen-shares baseline can
        # represent the whole book, plus the explicit price-only market reference.
        for symbol in _history_symbols(symbols):
            requested_at = datetime.now(UTC)
            if self._history_refresh_policy is not None and not self._history_refresh_policy.is_due(
                symbol,
                now=requested_at,
            ):
                continue
            history = self._client.get_daily_price_history(symbol)
            history_received_at = datetime.now(UTC)
            history_batch = self._mapper.map_price_history(
                history,
                observed_at=history_received_at,
                parser_version=self._parser_version,
                asset_type=held_assets.get(symbol, AssetType.ETF),
            )
            self._recorder.execute(history_batch)
            daily_bar_count += len(history_batch.daily_bars)
            if self._history_refresh_policy is not None:
                self._history_refresh_policy.mark_succeeded(symbol, at=requested_at)

        # Intraday bars are chart enrichment, never a reason to fail the core
        # account refresh. Schwab may constrain minute-history lookbacks per app;
        # retain the verified daily series when that optional request is rejected.
        for symbol in symbols:
            requested_at = datetime.now(UTC)
            policy_key = f"intraday:{symbol}"
            if self._history_refresh_policy is not None and not self._history_refresh_policy.is_due(
                policy_key,
                now=requested_at,
            ):
                continue
            try:
                history = self._client.get_intraday_price_history(
                    symbol,
                    start_at=requested_at - INTRADAY_LOOKBACK,
                    end_at=requested_at,
                    frequency_minutes=30,
                )
                history_received_at = datetime.now(UTC)
                history_batch = self._mapper.map_intraday_price_history(
                    history,
                    observed_at=history_received_at,
                    parser_version=self._parser_version,
                    interval_minutes=30,
                    asset_type=held_assets.get(symbol, AssetType.UNKNOWN),
                )
                self._recorder.execute(history_batch)
                intraday_bar_count += len(history_batch.intraday_bars)
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("Intraday history unavailable for %s: %s", symbol, exc)
                continue
            if self._history_refresh_policy is not None:
                self._history_refresh_policy.mark_succeeded(policy_key, at=requested_at)

        return MarketSyncResult(
            underlying_quote_count=underlying_count,
            option_quote_count=option_count,
            daily_bar_count=daily_bar_count,
            completed_at=datetime.now(UTC),
            intraday_bar_count=intraday_bar_count,
        )


def _held_market_assets(
    positions: Sequence[Mapping[str, object]],
) -> dict[str, AssetType]:
    excluded = {"OPTION", "CASH", "FIXED_INCOME"}
    assets: dict[str, AssetType] = {}
    for row in positions:
        raw_type = str(row.get("asset_type") or "").upper()
        symbol = str(row.get("symbol") or "").strip().upper()
        if raw_type in excluded or not symbol:
            continue
        assets[symbol] = _asset_type(raw_type)
    return assets


def _history_symbols(held_symbols: list[str]) -> list[str]:
    return sorted(set(held_symbols) | MARKET_REFERENCE_SYMBOLS)


def _asset_type(value: str) -> AssetType:
    normalized = value.strip().upper()
    return {
        "EQUITY": AssetType.EQUITY,
        "ETF": AssetType.ETF,
        "MUTUAL_FUND": AssetType.MUTUAL_FUND,
        "COLLECTIVE_INVESTMENT": AssetType.MUTUAL_FUND,
    }.get(normalized, AssetType.UNKNOWN)


def _as_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise ValueError("Option expiration is not a date")
