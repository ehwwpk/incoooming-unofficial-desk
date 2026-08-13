from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime

from schwab_dashboard.application.imports import parse_csv_file
from schwab_dashboard.application.ports.source_store import SourceDatasetStore
from schwab_dashboard.domain.data_source import (
    BrokerKind,
    CsvImportPreview,
    ImportRecordKind,
    ImportRowDisposition,
    ParsedCsvFile,
    SourceDataset,
)


class ImportCsvDataset:
    def __init__(self, *, store: SourceDatasetStore) -> None:
        self._store = store

    def preview(
        self,
        *,
        name: str,
        broker: BrokerKind,
        files: Sequence[tuple[str, bytes]],
    ) -> CsvImportPreview:
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Give this imported book a short name.")
        if len(clean_name) > 120:
            raise ValueError("Dataset names are limited to 120 characters.")
        if not files:
            raise ValueError("Choose at least one CSV file.")
        if len(files) > 8:
            raise ValueError("Import no more than eight CSV files at once.")
        parsed = tuple(
            parse_csv_file(filename=filename, content=content, broker=broker)
            for filename, content in files
        )
        hashes = [item.sha256 for item in parsed]
        if len(hashes) != len(set(hashes)):
            raise ValueError("The same CSV file was selected more than once.")
        parsed = _deduplicate_overlapping_files(parsed)
        position_count = sum(
            record.kind is ImportRecordKind.POSITION for file in parsed for record in file.records
        )
        activity_count = sum(
            record.kind is not ImportRecordKind.POSITION
            for file in parsed
            for record in file.records
        )
        ignored_count = sum(file.ignored_count for file in parsed)
        review_count = sum(file.review_count for file in parsed)
        rejected_count = sum(file.rejected_count for file in parsed)
        capabilities = tuple(
            sorted({capability for file in parsed for capability in file.capabilities})
        )
        warnings = tuple(dict.fromkeys(warning for file in parsed for warning in file.warnings))
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "name": clean_name,
                    "broker": broker.value,
                    "files": hashes,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return CsvImportPreview(
            name=clean_name,
            requested_broker=broker,
            fingerprint=fingerprint,
            files=parsed,
            position_count=position_count,
            activity_count=activity_count,
            ignored_count=ignored_count,
            review_count=review_count,
            rejected_count=rejected_count,
            capabilities=capabilities,
            warnings=warnings,
        )

    def execute(
        self,
        *,
        name: str,
        broker: BrokerKind,
        files: Sequence[tuple[str, bytes]],
        preview_fingerprint: str | None = None,
    ) -> SourceDataset:
        preview = self.preview(name=name, broker=broker, files=files)
        if preview_fingerprint is not None and preview.fingerprint != preview_fingerprint:
            raise ValueError(
                "The selected files or import settings changed after preview. Review them again."
            )
        return self._store.create_dataset(
            name=preview.name,
            broker=broker,
            files=preview.files,
            created_at=datetime.now(UTC),
        )


def _deduplicate_overlapping_files(
    files: tuple[ParsedCsvFile, ...],
) -> tuple[ParsedCsvFile, ...]:
    seen: set[str] = set()
    result: list[ParsedCsvFile] = []
    for file in files:
        duplicates = {record.external_key for record in file.records if record.external_key in seen}
        if not duplicates:
            result.append(file)
            seen.update(record.external_key for record in file.records)
            continue
        kept = tuple(record for record in file.records if record.external_key not in duplicates)
        rows = tuple(
            replace(
                row,
                disposition=ImportRowDisposition.IGNORED,
                reason="Duplicate of a normalized row in an earlier selected file.",
                record=None,
            )
            if row.record is not None and row.record.external_key in duplicates
            else row
            for row in file.rows
        )
        result.append(
            replace(
                file,
                records=kept,
                rows=rows,
                warnings=(
                    *file.warnings,
                    f"{len(duplicates)} overlapping normalized row(s) were ignored.",
                ),
            )
        )
        seen.update(record.external_key for record in kept)
    return tuple(result)
