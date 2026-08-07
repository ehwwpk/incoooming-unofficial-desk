from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy.orm import Session

from schwab_dashboard.domain.reconciliation import ReconciliationIssue
from schwab_dashboard.infrastructure.database.tables.reconciliation import (
    ReconciliationIssueTable,
)


class SqlReconciliationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_many(self, sync_run_id: str, issues: Sequence[ReconciliationIssue]) -> None:
        self._session.add_all(
            [
                ReconciliationIssueTable(
                    sync_run_id=sync_run_id,
                    code=issue.code,
                    severity=issue.severity.value,
                    message=issue.message,
                    account_external_key=issue.account_external_key,
                    instrument_key=issue.instrument_key,
                    context=issue.context,
                )
                for issue in issues
            ]
        )
