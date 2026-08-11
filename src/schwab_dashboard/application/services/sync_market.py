from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from schwab_dashboard.application.ports.repositories import UnitOfWorkFactory
from schwab_dashboard.application.services.record_market_observations import (
    RecordMarketObservations,
)
from schwab_dashboard.infrastructure.schwab.gateway import SchwabReadOnlyMarketDataClient
from schwab_dashboard.infrastructure.schwab.market_mapper import SchwabMarketMapper


@dataclass(frozen=True, slots=True)
class MarketSyncResult:
    underlying_quote_count: int
    option_quote_count: int
    daily_bar_count: int
    completed_at: datetime


class SyncSchwabMarketData:
    def __init__(
        self,
        *,
        client: SchwabReadOnlyMarketDataClient,
        mapper: SchwabMarketMapper,
        recorder: RecordMarketObservations,
        uow_factory: UnitOfWorkFactory,
        parser_version: str,
    ) -> None:
        self._client = client
        self._mapper = mapper
        self._recorder = recorder
        self._uow_factory = uow_factory
        self._parser_version = parser_version

    def execute(self) -> MarketSyncResult:
        with self._uow_factory() as uow:
            positions = tuple(uow.positions.list_latest())

        symbols = sorted(
            {
                str(row["symbol"])
                for row in positions
                if str(row.get("asset_type") or "").upper() != "OPTION"
            }
        )
        option_positions: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
        for row in positions:
            if str(row.get("asset_type") or "").upper() != "OPTION":
                continue
            if str(row.get("option_type") or "").upper() != "CALL":
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

            history = self._client.get_daily_price_history(underlying)
            history_received_at = datetime.now(UTC)
            history_batch = self._mapper.map_price_history(
                history,
                observed_at=history_received_at,
                parser_version=self._parser_version,
            )
            self._recorder.execute(history_batch)
            daily_bar_count += len(history_batch.daily_bars)

        return MarketSyncResult(
            underlying_quote_count=underlying_count,
            option_quote_count=option_count,
            daily_bar_count=daily_bar_count,
            completed_at=datetime.now(UTC),
        )


def _as_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise ValueError("Option expiration is not a date")
