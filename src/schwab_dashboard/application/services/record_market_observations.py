from __future__ import annotations

from dataclasses import dataclass

from schwab_dashboard.application.ports.market import (
    MarketUnitOfWork,
    MarketUnitOfWorkFactory,
    OptionMarketSnapshotWrite,
    UnderlyingMarketSnapshotWrite,
)
from schwab_dashboard.domain.market import InstrumentRef, MarketObservationBatch


@dataclass(frozen=True, slots=True)
class MarketObservationResult:
    raw_event_id: str
    instrument_count: int
    underlying_snapshot_count: int
    option_snapshot_count: int


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
            uow.commit()

        return MarketObservationResult(
            raw_event_id=raw_event_id,
            instrument_count=len(batch.instruments),
            underlying_snapshot_count=len(batch.underlying_snapshots),
            option_snapshot_count=len(batch.option_snapshots),
        )

    @staticmethod
    def _instrument_id(uow: MarketUnitOfWork, reference: InstrumentRef) -> str:
        return uow.instruments.require_id(
            source=reference.source,
            external_key=reference.external_key,
        )

    @staticmethod
    def _validate_timestamps(batch: MarketObservationBatch) -> None:
        mismatched_underlyings = [
            snapshot.instrument.external_key
            for snapshot in batch.underlying_snapshots
            if snapshot.observed_at != batch.observed_at
        ]
        mismatched_options = [
            snapshot.instrument.external_key
            for snapshot in batch.option_snapshots
            if snapshot.observed_at != batch.observed_at
        ]
        mismatched = mismatched_underlyings + mismatched_options
        if mismatched:
            joined = ", ".join(sorted(mismatched))
            raise ValueError(f"market snapshots do not match the raw event timestamp: {joined}")
