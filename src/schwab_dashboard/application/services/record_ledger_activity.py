from __future__ import annotations

from dataclasses import dataclass

from schwab_dashboard.application.ports.ledger import (
    CashMovementWrite,
    ExecutionWrite,
    OptionLifecycleEventWrite,
    TruthUnitOfWork,
    TruthUnitOfWorkFactory,
)
from schwab_dashboard.domain.ledger import LedgerActivityBatch


@dataclass(frozen=True, slots=True)
class LedgerActivityResult:
    instrument_count: int
    execution_count: int
    cash_movement_count: int
    lifecycle_event_count: int


class RecordLedgerActivity:
    def __init__(self, *, uow_factory: TruthUnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    def execute(self, batch: LedgerActivityBatch) -> LedgerActivityResult:
        self._validate_instrument_sources(batch)
        with self._uow_factory() as uow:
            account_id = uow.accounts.require_id(
                source=batch.source,
                external_account_key=batch.account_external_key,
            )
            for instrument in batch.instruments:
                uow.instruments.upsert(instrument)

            for execution in batch.executions:
                instrument_id = self._instrument_id(
                    uow, source=batch.source, external_key=execution.instrument_external_key
                )
                uow.executions.add(
                    ExecutionWrite(
                        source=batch.source,
                        account_id=account_id,
                        instrument_id=instrument_id,
                        raw_event_id=batch.raw_event_id,
                        record=execution,
                    )
                )

            for movement in batch.cash_movements:
                cash_instrument_id: str | None = None
                if movement.instrument_external_key is not None:
                    cash_instrument_id = self._instrument_id(
                        uow,
                        source=batch.source,
                        external_key=movement.instrument_external_key,
                    )
                uow.cash_movements.add(
                    CashMovementWrite(
                        source=batch.source,
                        account_id=account_id,
                        instrument_id=cash_instrument_id,
                        raw_event_id=batch.raw_event_id,
                        record=movement,
                    )
                )

            for event in batch.lifecycle_events:
                option_id = self._instrument_id(
                    uow,
                    source=batch.source,
                    external_key=event.option_instrument_external_key,
                )
                stock_id = None
                if event.stock_instrument_external_key is not None:
                    stock_id = self._instrument_id(
                        uow,
                        source=batch.source,
                        external_key=event.stock_instrument_external_key,
                    )
                uow.lifecycle_events.add(
                    OptionLifecycleEventWrite(
                        source=batch.source,
                        account_id=account_id,
                        option_instrument_id=option_id,
                        stock_instrument_id=stock_id,
                        raw_event_id=batch.raw_event_id,
                        record=event,
                    )
                )
            uow.commit()

        return LedgerActivityResult(
            instrument_count=len(batch.instruments),
            execution_count=len(batch.executions),
            cash_movement_count=len(batch.cash_movements),
            lifecycle_event_count=len(batch.lifecycle_events),
        )

    @staticmethod
    def _instrument_id(
        uow: TruthUnitOfWork,
        *,
        source: str,
        external_key: str,
    ) -> str:
        return uow.instruments.require_id(source=source, external_key=external_key)

    @staticmethod
    def _validate_instrument_sources(batch: LedgerActivityBatch) -> None:
        conflicting = sorted(
            instrument.external_key
            for instrument in batch.instruments
            if instrument.source != batch.source
        )
        if conflicting:
            joined = ", ".join(conflicting)
            raise ValueError(f"ledger batch contains instruments from another source: {joined}")
