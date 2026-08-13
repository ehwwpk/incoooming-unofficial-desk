from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from schwab_dashboard.domain.data_source import (
    BrokerKind,
    DatasetState,
    ImportRecordKind,
    ParsedCsvFile,
    SourceDataset,
)
from schwab_dashboard.infrastructure.database.engine import SessionFactory
from schwab_dashboard.infrastructure.database.tables.source import (
    SourceDatasetTable,
    SourceImportFileTable,
    SourceImportRecordTable,
)


class SqlSourceDatasetStore:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def create_dataset(
        self,
        *,
        name: str,
        broker: BrokerKind,
        files: tuple[ParsedCsvFile, ...],
        created_at: datetime,
    ) -> SourceDataset:
        if not files:
            raise ValueError("a CSV dataset requires at least one file")
        position_count = sum(
            record.kind is ImportRecordKind.POSITION for file in files for record in file.records
        )
        activity_count = sum(
            record.kind is not ImportRecordKind.POSITION
            for file in files
            for record in file.records
        )
        rejected_count = sum(file.rejected_count for file in files)
        warnings = tuple(dict.fromkeys(message for file in files for message in file.warnings))
        state = DatasetState.PARTIAL if warnings or not position_count else DatasetState.READY
        dataset_row = SourceDatasetTable(
            name=name.strip(),
            broker=broker.value,
            state=state.value,
            created_at=created_at,
            file_count=len(files),
            position_count=position_count,
            activity_count=activity_count,
            rejected_count=rejected_count,
            warnings=list(warnings),
        )
        with self._session_factory() as session:
            session.add(dataset_row)
            session.flush()
            for file in files:
                file_row = SourceImportFileTable(
                    dataset_id=dataset_row.id,
                    filename=file.filename,
                    file_kind=file.file_kind,
                    sha256=file.sha256,
                    headers=list(file.headers),
                    record_count=len(file.records),
                    rejected_count=file.rejected_count,
                    warnings=list(file.warnings),
                )
                session.add(file_row)
                session.flush()
                for record in file.records:
                    normalized = dict(record.normalized)
                    normalized["external_key"] = record.external_key
                    session.add(
                        SourceImportRecordTable(
                            dataset_id=dataset_row.id,
                            file_id=file_row.id,
                            record_kind=record.kind.value,
                            external_key=record.external_key,
                            normalized=normalized,
                            raw=dict(record.raw),
                        )
                    )
            session.commit()
            session.refresh(dataset_row)
        return _dataset(dataset_row)

    def list_datasets(self) -> tuple[SourceDataset, ...]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(SourceDatasetTable).order_by(SourceDatasetTable.created_at.desc())
            ).all()
        return tuple(_dataset(row) for row in rows)

    def get_dataset(self, dataset_id: str) -> SourceDataset | None:
        with self._session_factory() as session:
            row = session.get(SourceDatasetTable, dataset_id)
        return _dataset(row) if row is not None else None

    def load_records(self, dataset_id: str) -> tuple[dict[str, object], ...]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(SourceImportRecordTable)
                .where(SourceImportRecordTable.dataset_id == dataset_id)
                .order_by(SourceImportRecordTable.id)
            ).all()
        return tuple({"kind": row.record_kind, "normalized": dict(row.normalized)} for row in rows)


def _dataset(row: SourceDatasetTable) -> SourceDataset:
    return SourceDataset(
        id=row.id,
        name=row.name,
        broker=BrokerKind(row.broker),
        state=DatasetState(row.state),
        created_at=_aware(row.created_at),
        file_count=row.file_count,
        position_count=row.position_count,
        activity_count=row.activity_count,
        rejected_count=row.rejected_count,
        warnings=tuple(row.warnings),
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
