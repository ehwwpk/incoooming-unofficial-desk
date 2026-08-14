from __future__ import annotations

from dataclasses import dataclass

from schwab_dashboard.application.ports.market import (
    MarketUnitOfWork,
    MarketUnitOfWorkFactory,
    OptionMarketSnapshotWrite,
    UnderlyingDailyBarWrite,
    UnderlyingIntradayBarWrite,
    UnderlyingMarketSnapshotWrite,
)
from schwab_dashboard.domain.market import InstrumentRef, MarketObservationBatch


@dataclass(frozen=True, slots=True)
class MarketObservationResult:
    raw_event_id: str
    instrument_count: int
    underlying_snapshot_count: int
    option_snapshot_count: int
    intraday_bar_count: int


class RecordMarketObservations:
    def __init__(self, *, uow_factory: MarketUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, batch: MarketObservationBatch) -> MarketObservationResult:
        self._validate_timestamps(batch)
        with self._uow_factory() as uow:
            raw_event_id = uow.raw_market_events.add(
                source=batch.source,
                external_event_key=batch.external_event_key,
                observed_at=batch.observed_at,
                parser_version=batch.parser_version,
                payload=batch.raw_payload,
            )
            for instrument in batch.instruments:
                uow.instruments.upsert(instrument)

            for underlying_snapshot in batch.underlying_snapshots:
                instrument_id = self._instrument_id(uow, underlying_snapshot.instrument)
                uow.underlying_market_snapshots.add(
                    UnderlyingMarketSnapshotWrite(
                        raw_event_id=raw_event_id,
                        instrument_id=instrument_id,
                        snapshot=underlying_snapshot,
                    )
                )
            for option_snapshot in batch.option_snapshots:
                instrument_id = self._instrument_id(uow, option_snapshot.instrument)
                uow.option_market_snapshots.add(
                    OptionMarketSnapshotWrite(
                        raw_event_id=raw_event_id,
                        instrument_id=instrument_id,
                        snapshot=option_snapshot,
                    )
                )
            for daily_bar in batch.daily_bars:
                instrument_id = self._instrument_id(uow, daily_bar.instrument)
                uow.underlying_daily_bars.add(
                    UnderlyingDailyBarWrite(
                        raw_event_id=raw_event_id,
                        instrument_id=instrument_id,
                        bar=daily_bar,
                    )
                )
            for intraday_bar in batch.intraday_bars:
                instrument_id = self._instrument_id(uow, intraday_bar.instrument)
                uow.underlying_intraday_bars.add(
                    UnderlyingIntradayBarWrite(
                        raw_event_id=raw_event_id,
                        instrument_id=instrument_id,
                        bar=intraday_bar,
                    )
                )
            uow.commit()

        return MarketObservationResult(
            raw_event_id=raw_event_id,
            instrument_count=len(batch.instruments),
            underlying_snapshot_count=len(batch.underlying_snapshots),
            option_snapshot_count=len(batch.option_snapshots),
            intraday_bar_count=len(batch.intraday_bars),
        )

    @staticmethod
    def _instrument_id(uow: MarketUnitOfWork, reference: InstrumentRef) -> str:
        return uow.instruments.require_id(
            source=reference.source,
            external_key=reference.external_key,
        )

    @staticmethod
    def _validate_timestamps(batch: MarketObservationBatch) -> None:
        future_underlyings = [
            snapshot.instrument.external_key
            for snapshot in batch.underlying_snapshots
            if snapshot.observed_at > batch.observed_at
        ]
        future_options = [
            snapshot.instrument.external_key
            for snapshot in batch.option_snapshots
            if snapshot.observed_at > batch.observed_at
        ]
        future = future_underlyings + future_options
        if future:
            joined = ", ".join(sorted(future))
            raise ValueError(f"market snapshots cannot postdate their raw event: {joined}")
