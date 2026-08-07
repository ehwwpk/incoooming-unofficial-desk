from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from schwab_dashboard.infrastructure.database.tables.base import Base, utc_now


class ReconciliationIssueTable(Base):
    __tablename__ = "reconciliation_issues"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    sync_run_id: Mapped[str] = mapped_column(
        ForeignKey("sync_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    account_external_key: Mapped[str] = mapped_column(String(256), nullable=False)
    instrument_key: Mapped[str | None] = mapped_column(String(256))
    context: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
