from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from schwab_dashboard.application.errors import SyncValidationError
from schwab_dashboard.application.ports.broker import BrokerAccountRecord, BrokerGateway
from schwab_dashboard.application.ports.repositories import (
    AccountBalanceSnapshotWrite,
    PositionSnapshotWrite,
    UnitOfWorkFactory,
)
from schwab_dashboard.domain.reconciliation import (
    IssueSeverity,
    ReconciliationIssue,
)


@dataclass(frozen=True, slots=True)
class SyncResult:
    run_id: str
    account_count: int
    position_count: int
    warning_count: int
    completed_at: datetime


class SyncAccountsAndPositions:
    def __init__(
        self,
        *,
        broker: BrokerGateway,
        uow_factory: UnitOfWorkFactory,
        parser_version: str,
    ) -> None:
        self._broker = broker
        self._uow_factory = uow_factory
        self._parser_version = parser_version

    def execute(self) -> SyncResult:
        observed_at = datetime.now(UTC)
        run_id = self._start_run(observed_at)

        try:
            records = tuple(self._broker.fetch_accounts_with_positions())
            raw_event_ids = self._store_raw_events(run_id, observed_at, records)
            issues = self._validate(records)
            errors = [issue for issue in issues if issue.severity is IssueSeverity.ERROR]
            if errors:
                message = f"Sync blocked by {len(errors)} structural reconciliation error(s)."
                self._record_failed_validation(run_id, issues, message)
                raise SyncValidationError(message)

            position_count = self._store_normalized_snapshot(
                run_id=run_id,
                observed_at=observed_at,
                records=records,
                raw_event_ids=raw_event_ids,
                issues=issues,
            )
        except Exception as exc:
            self._mark_failed_if_running(run_id, exc)
            raise

        completed_at = datetime.now(UTC)
        return SyncResult(
            run_id=run_id,
            account_count=len(records),
            position_count=position_count,
            warning_count=sum(1 for issue in issues if issue.severity is IssueSeverity.WARNING),
            completed_at=completed_at,
        )

    def _start_run(self, started_at: datetime) -> str:
        with self._uow_factory() as uow:
            run_id = uow.sync_runs.start(source="schwab", started_at=started_at)
            uow.commit()
            return run_id

    def _store_raw_events(
        self,
        run_id: str,
        observed_at: datetime,
        records: Sequence[BrokerAccountRecord],
    ) -> dict[str, str]:
        raw_event_ids: dict[str, str] = {}
        with self._uow_factory() as uow:
            for record in records:
                external_key = record.account.external_key
                raw_event_ids[external_key] = uow.raw_events.add(
                    sync_run_id=run_id,
                    item_key=f"account:{external_key}",
                    event_type="account_with_positions",
                    account_external_key=external_key,
                    observed_at=observed_at,
                    parser_version=self._parser_version,
                    payload=dict(record.raw_payload),
                )
            uow.commit()
        return raw_event_ids

    def _store_normalized_snapshot(
        self,
        *,
        run_id: str,
        observed_at: datetime,
        records: Sequence[BrokerAccountRecord],
        raw_event_ids: dict[str, str],
        issues: Sequence[ReconciliationIssue],
    ) -> int:
        position_count = 0
        with self._uow_factory() as uow:
            for record in records:
                account_id = uow.accounts.upsert(record.account, observed_at=observed_at)
                if record.balances is not None:
                    uow.balances.add(
                        AccountBalanceSnapshotWrite(
                            account_id=account_id,
                            sync_run_id=run_id,
                            raw_event_id=raw_event_ids[record.account.external_key],
                            observed_at=observed_at,
                            **asdict(record.balances),
                        )
                    )
                for position in record.positions:
                    uow.positions.add(
                        PositionSnapshotWrite(
                            account_id=account_id,
                            sync_run_id=run_id,
                            raw_event_id=raw_event_ids[record.account.external_key],
                            observed_at=observed_at,
                            instrument_key=position.instrument_key,
                            symbol=position.symbol,
                            asset_type=position.asset_type,
                            long_quantity=position.long_quantity,
                            short_quantity=position.short_quantity,
                            average_price=position.average_price,
                            market_value=position.market_value,
                            day_profit_loss=position.day_profit_loss,
                            day_profit_loss_percent=position.day_profit_loss_percent,
                            description=position.description,
                            underlying_symbol=position.underlying_symbol,
                            option_type=position.option_type,
                            expiration_date=(
                                datetime.combine(position.expiration_date, datetime.min.time())
                                if position.expiration_date is not None
                                else None
                            ),
                            strike=position.strike,
                            long_open_profit_loss=position.long_open_profit_loss,
                            short_open_profit_loss=position.short_open_profit_loss,
                            contract_multiplier=position.contract_multiplier,
                            is_non_standard=position.is_non_standard,
                        )
                    )
                    position_count += 1

            uow.reconciliation.add_many(run_id, issues)
            uow.sync_runs.complete(
                run_id,
                completed_at=datetime.now(UTC),
                account_count=len(records),
                position_count=position_count,
            )
            uow.commit()
        return position_count

    def _record_failed_validation(
        self,
        run_id: str,
        issues: Sequence[ReconciliationIssue],
        message: str,
    ) -> None:
        with self._uow_factory() as uow:
            uow.reconciliation.add_many(run_id, issues)
            uow.sync_runs.fail(
                run_id,
                completed_at=datetime.now(UTC),
                error_message=message,
            )
            uow.commit()

    def _mark_failed_if_running(self, run_id: str, exc: Exception) -> None:
        with self._uow_factory() as uow:
            summary = uow.sync_runs.latest()
            if summary is not None and summary.run_id == run_id and summary.status == "running":
                uow.sync_runs.fail(
                    run_id,
                    completed_at=datetime.now(UTC),
                    error_message=str(exc)[:2000],
                )
                uow.commit()

    @staticmethod
    def _validate(records: Sequence[BrokerAccountRecord]) -> tuple[ReconciliationIssue, ...]:
        issues: list[ReconciliationIssue] = []
        account_keys: set[str] = set()

        for record in records:
            account_key = record.account.external_key
            if account_key in account_keys:
                issues.append(
                    ReconciliationIssue(
                        code="duplicate_account",
                        severity=IssueSeverity.ERROR,
                        message="The Schwab response contained the same account identity twice.",
                        account_external_key=account_key,
                    )
                )
            account_keys.add(account_key)

            instrument_keys: set[str] = set()
            for position in record.positions:
                if position.instrument_key in instrument_keys:
                    issues.append(
                        ReconciliationIssue(
                            code="duplicate_position_identity",
                            severity=IssueSeverity.ERROR,
                            message=(
                                "Two position rows resolved to the same instrument identity; "
                                "the snapshot was not guessed or combined."
                            ),
                            account_external_key=account_key,
                            instrument_key=position.instrument_key,
                        )
                    )
                instrument_keys.add(position.instrument_key)

        return tuple(issues)
