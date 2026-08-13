from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from schwab_dashboard.infrastructure.database.tables.base import Base, utc_now


class SourceDatasetTable(Base):
    __tablename__ = "source_datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    broker: Mapped[str] = mapped_column(String(24), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    position_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    activity_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)


class SourceImportFileTable(Base):
    __tablename__ = "source_import_files"
    __table_args__ = (UniqueConstraint("dataset_id", "sha256", name="uq_source_import_file_hash"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    dataset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("source_datasets.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    headers: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warnings: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)


class SourceImportRecordTable(Base):
    __tablename__ = "source_import_records"
    __table_args__ = (
        UniqueConstraint("dataset_id", "external_key", name="uq_source_import_record_external_key"),
        Index("ix_source_import_records_dataset_kind", "dataset_id", "record_kind"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    dataset_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("source_datasets.id", ondelete="CASCADE"), nullable=False
    )
    file_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("source_import_files.id", ondelete="CASCADE"), nullable=False
    )
    record_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    external_key: Mapped[str] = mapped_column(String(160), nullable=False)
    normalized: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    raw: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
