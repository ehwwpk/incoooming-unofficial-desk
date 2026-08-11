from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from schwab_dashboard.application.ports.repositories import UnitOfWorkFactory
from schwab_dashboard.application.services.record_ledger_activity import RecordLedgerActivity
from schwab_dashboard.domain.ledger import LedgerActivityBatch
from schwab_dashboard.infrastructure.schwab.gateway import SchwabReadOnlyTraderClient
from schwab_dashboard.infrastructure.schwab.transaction_mapper import SchwabTransactionMapper

TRANSACTION_TYPES = ",".join(
    (
        "TRADE",
        "RECEIVE_AND_DELIVER",
        "DIVIDEND_OR_INTEREST",
        "ACH_RECEIPT",
        "ACH_DISBURSEMENT",
        "CASH_RECEIPT",
        "CASH_DISBURSEMENT",
        "ELECTRONIC_FUND",
        "WIRE_OUT",
        "WIRE_IN",
        "JOURNAL",
        "MEMORANDUM",
        "MARGIN_CALL",
        "MONEY_MARKET",
        "SMA_ADJUSTMENT",
    )
)


@dataclass(frozen=True, slots=True)
class TransactionSyncResult:
    run_id: str
    account_count: int
    transaction_count: int
    execution_count: int
    cash_movement_count: int
    lifecycle_event_count: int
    completed_at: datetime


class SyncSchwabTransactions:
    def __init__(
        self,
        *,
        client: SchwabReadOnlyTraderClient,
        mapper: SchwabTransactionMapper,
        ledger: RecordLedgerActivity,
        uow_factory: UnitOfWorkFactory,
        parser_version: str,
        history_days: int = 365,
    ) -> None:
        self._client = client
        self._mapper = mapper
        self._ledger = ledger
        self._uow_factory = uow_factory
        self._parser_version = parser_version
        self._history_days = history_days

    def execute(self) -> TransactionSyncResult:
        observed_at = datetime.now(UTC)
        run_id = self._start_run(observed_at)
        execution_count = 0
        cash_count = 0
        lifecycle_count = 0
        try:
            accounts = self._client.get_account_numbers()
            transactions_by_account = {
                _required_text(account, "hashValue"): self._fetch_history(
                    _required_text(account, "hashValue"), observed_at
                )
                for account in accounts
            }
            for account_hash, transactions in transactions_by_account.items():
                for payload in transactions:
                    raw_event_id = self._store_raw(
                        run_id,
                        account_hash=account_hash,
                        observed_at=observed_at,
                        payload=payload,
                    )
                    mapped = self._mapper.map(payload, observed_at=observed_at)
                    result = self._ledger.execute(
                        LedgerActivityBatch(
                            source="schwab",
                            account_external_key=account_hash,
                            raw_event_id=raw_event_id,
                            instruments=mapped.instruments,
                            executions=mapped.executions,
                            cash_movements=mapped.cash_movements,
                            lifecycle_events=mapped.lifecycle_events,
                        )
                    )
                    execution_count += result.execution_count
                    cash_count += result.cash_movement_count
                    lifecycle_count += result.lifecycle_event_count
            transaction_count = sum(len(items) for items in transactions_by_account.values())
            completed_at = datetime.now(UTC)
            self._complete_run(
                run_id,
                completed_at=completed_at,
                account_count=len(accounts),
            )
        except Exception as exc:
            self._fail_run(run_id, exc)
            raise
        return TransactionSyncResult(
            run_id=run_id,
            account_count=len(accounts),
            transaction_count=transaction_count,
            execution_count=execution_count,
            cash_movement_count=cash_count,
            lifecycle_event_count=lifecycle_count,
            completed_at=completed_at,
        )

    def _fetch_history(
        self,
        account_hash: str,
        observed_at: datetime,
    ) -> tuple[Mapping[str, Any], ...]:
        by_id: dict[str, Mapping[str, Any]] = {}
        cursor = observed_at
        oldest = observed_at - timedelta(days=self._history_days)
        while cursor > oldest:
            start = max(oldest, cursor - timedelta(days=58, hours=23))
            rows = self._client.get_transactions(
                account_hash,
                start_at=start,
                end_at=cursor,
                transaction_types=TRANSACTION_TYPES,
            )
            for row in rows:
                activity_id = _required_text(row, "activityId")
                existing = by_id.get(activity_id)
                if existing is not None and dict(existing) != dict(row):
                    raise ValueError(
                        f"Schwab transaction {activity_id} changed across history pages"
                    )
                by_id[activity_id] = row
            cursor = start - timedelta(seconds=1)
        return tuple(
            sorted(by_id.values(), key=lambda row: str(row.get("time") or row.get("tradeDate")))
        )

    def _start_run(self, started_at: datetime) -> str:
        with self._uow_factory() as uow:
            run_id = uow.sync_runs.start(source="schwab_activity", started_at=started_at)
            uow.commit()
            return run_id

    def _store_raw(
        self,
        run_id: str,
        *,
        account_hash: str,
        observed_at: datetime,
        payload: Mapping[str, Any],
    ) -> str:
        activity_id = _required_text(payload, "activityId")
        with self._uow_factory() as uow:
            raw_event_id = uow.raw_events.add(
                sync_run_id=run_id,
                item_key=f"transaction:{activity_id}",
                event_type="transaction",
                account_external_key=account_hash,
                observed_at=observed_at,
                parser_version=self._parser_version,
                payload=dict(payload),
            )
            uow.commit()
            return raw_event_id

    def _complete_run(
        self,
        run_id: str,
        *,
        completed_at: datetime,
        account_count: int,
    ) -> None:
        with self._uow_factory() as uow:
            uow.sync_runs.complete(
                run_id,
                completed_at=completed_at,
                account_count=account_count,
                position_count=0,
            )
            uow.commit()

    def _fail_run(self, run_id: str, exc: Exception) -> None:
        with self._uow_factory() as uow:
            uow.sync_runs.fail(
                run_id,
                completed_at=datetime.now(UTC),
                error_message=str(exc)[:2000],
            )
            uow.commit()


def _required_text(payload: Mapping[str, Any], field: str) -> str:
    value = payload.get(field)
    if value is None or not str(value).strip():
        raise ValueError(f"Schwab response is missing {field}")
    return str(value)
