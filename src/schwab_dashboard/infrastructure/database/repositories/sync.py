from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from schwab_dashboard.application.ports.repositories import SyncRunSummary
from schwab_dashboard.infrastructure.database.tables.sync import (
    RawBrokerEventTable,
    SyncRunTable,
)


class SqlSyncRunRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def start(self, *, source: str, started_at: datetime) -> str:
        row = SyncRunTable(source=source, status="running", started_at=started_at)
        self._session.add(row)
        self._session.flush()
        return row.id

    def complete(
        self,
        run_id: str,
        *,
        completed_at: datetime,
        account_count: int,
        position_count: int,
    ) -> None:
        row = self._require(run_id)
        row.status = "completed"
        row.completed_at = completed_at
        row.account_count = account_count
        row.position_count = position_count
        row.error_message = None

    def fail(self, run_id: str, *, completed_at: datetime, error_message: str) -> None:
        row = self._require(run_id)
        row.status = "failed"
        row.completed_at = completed_at
        row.error_message = error_message

    def latest(self) -> SyncRunSummary | None:
        row = self._session.scalar(
            select(SyncRunTable).order_by(SyncRunTable.started_at.desc()).limit(1)
        )
        return self._summary(row)

    def latest_for_source(self, *, source: str) -> SyncRunSummary | None:
        row = self._session.scalar(
            select(SyncRunTable)
            .where(SyncRunTable.source == source)
            .order_by(SyncRunTable.started_at.desc())
            .limit(1)
        )
        return self._summary(row)

    def latest_successful(self, *, source: str) -> SyncRunSummary | None:
        row = self._session.scalar(
            select(SyncRunTable)
            .where(
                SyncRunTable.source == source,
                SyncRunTable.status == "completed",
            )
            .order_by(SyncRunTable.started_at.desc())
            .limit(1)
        )
        return self._summary(row)

    @staticmethod
    def _summary(row: SyncRunTable | None) -> SyncRunSummary | None:
        if row is None:
            return None
        return SyncRunSummary(
            run_id=row.id,
            source=row.source,
            status=row.status,
            started_at=row.started_at,
            completed_at=row.completed_at,
            account_count=row.account_count,
            position_count=row.position_count,
            error_message=row.error_message,
        )

    def _require(self, run_id: str) -> SyncRunTable:
        row = self._session.get(SyncRunTable, run_id)
        if row is None:
            raise LookupError(f"Sync run {run_id} does not exist")
        return row


class SqlRawEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(
        self,
        *,
        sync_run_id: str,
        item_key: str,
        event_type: str,
        account_external_key: str,
        observed_at: datetime,
        parser_version: str,
        payload: dict[str, Any],
    ) -> str:
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        row = RawBrokerEventTable(
            sync_run_id=sync_run_id,
            item_key=item_key,
            event_type=event_type,
            account_external_key=account_external_key,
            observed_at=observed_at,
            parser_version=parser_version,
            payload_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
            payload=payload,
        )
        self._session.add(row)
        self._session.flush()
        return row.id
