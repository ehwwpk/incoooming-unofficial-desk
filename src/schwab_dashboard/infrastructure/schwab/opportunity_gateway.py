from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from threading import Lock

from schwab_dashboard.application.services.record_market_observations import (
    RecordMarketObservations,
)
from schwab_dashboard.domain.instruments import AssetType, DeliverableKind, InstrumentRecord
from schwab_dashboard.domain.market import MarketObservationBatch
from schwab_dashboard.domain.opportunity import (
    RadarMarketBundle,
    RadarMarketContract,
    RadarMode,
)
from schwab_dashboard.infrastructure.schwab.gateway import SchwabReadOnlyMarketDataClient
from schwab_dashboard.infrastructure.schwab.market_mapper import SchwabMarketMapper


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    expires_at: datetime
    bundle: RadarMarketBundle


class SchwabOpportunityMarketGateway:
    """On-demand research adapter; deliberately absent from the account sync coordinator."""

    def __init__(
        self,
        *,
        client: SchwabReadOnlyMarketDataClient,
        mapper: SchwabMarketMapper,
        recorder: RecordMarketObservations,
        parser_version: str,
        cache_seconds: int,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._client = client
        self._mapper = mapper
        self._recorder = recorder
        self._parser_version = parser_version
        self._cache_seconds = cache_seconds
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = Lock()
        self._cache: dict[tuple[str, RadarMode, date, date], _CacheEntry] = {}

    def fetch(
        self,
        *,
        symbol: str,
        mode: RadarMode,
        from_date: date,
        to_date: date,
    ) -> RadarMarketBundle:
        key = (symbol, mode, from_date, to_date)
        with self._lock:
            now = self._clock()
            cached = self._cache.get(key)
            if cached is not None and cached.expires_at > now:
                return cached.bundle

            chain_payload = self._client.get_option_chain(
                symbol,
                from_date=from_date,
                to_date=to_date,
                contract_type="CALL" if mode is RadarMode.COVERED_CALL else "PUT",
                strike_count=250,
            )
            chain_received_at = self._clock()
            chain_batch = self._mapper.map_chain(
                chain_payload,
                observed_at=chain_received_at,
                parser_version=self._parser_version,
            )
            self._recorder.execute(chain_batch)

            history_payload = self._client.get_daily_price_history(symbol)
            history_received_at = self._clock()
            history_batch = self._mapper.map_price_history(
                history_payload,
                observed_at=history_received_at,
                parser_version=self._parser_version,
            )
            self._recorder.execute(history_batch)

            bundle = _bundle_from_batches(
                symbol=symbol,
                chain=chain_batch,
                history=history_batch,
            )
            self._cache[key] = _CacheEntry(
                expires_at=self._clock() + timedelta(seconds=self._cache_seconds),
                bundle=bundle,
            )
            return bundle


def _bundle_from_batches(
    *,
    symbol: str,
    chain: MarketObservationBatch,
    history: MarketObservationBatch,
) -> RadarMarketBundle:
    instruments = {item.external_key: item for item in chain.instruments}
    contracts = tuple(
        contract
        for snapshot in chain.option_snapshots
        if (
            contract := _contract_from_snapshot(
                snapshot.instrument.external_key, instruments, snapshot
            )
        )
        is not None
    )
    unsupported_contracts = sum(
        1
        for snapshot in chain.option_snapshots
        if (instrument := instruments.get(snapshot.instrument.external_key)) is not None
        and not _supports_radar_contract(instrument)
    )
    underlying_prices = [
        item.underlying_price
        for item in chain.option_snapshots
        if item.underlying_price is not None
    ]
    warnings: list[str] = []
    if not history.daily_bars:
        warnings.append("Daily price history is unavailable; movement context is incomplete.")
    if unsupported_contracts:
        warnings.append(
            f"{unsupported_contracts} non-100-share, adjusted, or unresolved contract"
            f"{'s were' if unsupported_contracts != 1 else ' was'} excluded because the share "
            "deliverable is unavailable."
        )
    return RadarMarketBundle(
        source="schwab",
        symbol=symbol,
        observed_at=chain.observed_at,
        underlying_price=underlying_prices[0] if underlying_prices else None,
        contracts=contracts,
        daily_bars=history.daily_bars,
        capabilities=("option_chain", "greeks", "daily_bars"),
        warnings=tuple(warnings),
    )


def _contract_from_snapshot(
    external_key: str,
    instruments: dict[str, InstrumentRecord],
    snapshot: object,
) -> RadarMarketContract | None:
    from schwab_dashboard.domain.market import OptionMarketSnapshot

    if not isinstance(snapshot, OptionMarketSnapshot):
        return None
    instrument = instruments.get(external_key)
    if (
        instrument is None
        or instrument.option_side is None
        or instrument.expiration_date is None
        or instrument.strike is None
        or instrument.contract_multiplier is None
        or instrument.underlying_symbol is None
        or not _supports_radar_contract(instrument)
    ):
        return None
    return RadarMarketContract(
        option_symbol=instrument.symbol,
        underlying_symbol=instrument.underlying_symbol,
        option_side=instrument.option_side,
        expiration_date=instrument.expiration_date,
        strike=instrument.strike,
        multiplier=instrument.contract_multiplier,
        observed_at=snapshot.observed_at,
        quote_quality=snapshot.quote_quality,
        bid=snapshot.bid,
        ask=snapshot.ask,
        last=snapshot.last,
        mark=snapshot.mark,
        underlying_price=snapshot.underlying_price,
        implied_volatility=snapshot.implied_volatility,
        delta=snapshot.delta,
        gamma=snapshot.gamma,
        theta=snapshot.theta,
        vega=snapshot.vega,
        volume=snapshot.volume,
        open_interest=snapshot.open_interest,
    )


def _supports_radar_contract(instrument: InstrumentRecord) -> bool:
    """Accept only the simple 100-share contracts Radar can size safely."""

    deliverable = instrument.deliverable
    if (
        deliverable is None
        or deliverable.kind is not DeliverableKind.STANDARD
        or instrument.contract_multiplier != Decimal("100")
        or len(deliverable.components) != 1
        or instrument.underlying_symbol is None
    ):
        return False
    component = deliverable.components[0]
    return (
        component.asset_type is AssetType.EQUITY
        and component.quantity == Decimal("100")
        and component.cash_amount is None
        and component.symbol is not None
        and component.symbol.strip().upper() == instrument.underlying_symbol.strip().upper()
    )
