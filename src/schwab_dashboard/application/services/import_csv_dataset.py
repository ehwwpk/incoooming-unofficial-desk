from __future__ import annotations

import hashlib
import json
from collections import Counter
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
    ParsedImportRecord,
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
        _validate_single_broker(parsed)
        _validate_position_snapshots(parsed)
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
            broker=_dataset_broker(preview.files, requested=broker),
            files=preview.files,
            created_at=datetime.now(UTC),
        )


def _deduplicate_overlapping_files(
    files: tuple[ParsedCsvFile, ...],
) -> tuple[ParsedCsvFile, ...]:
    seen_counts: Counter[str] = Counter()
    result: list[ParsedCsvFile] = []
    for file in files:
        file_counts: Counter[str] = Counter()
        duplicate_rows: set[int] = set()
        kept: list[ParsedImportRecord] = []
        for record in file.records:
            file_counts[record.fingerprint] += 1
            if file_counts[record.fingerprint] <= seen_counts[record.fingerprint]:
                duplicate_rows.add(record.source_row_number)
            else:
                kept.append(record)
        for fingerprint, count in file_counts.items():
            seen_counts[fingerprint] = max(seen_counts[fingerprint], count)
        if not duplicate_rows:
            result.append(file)
            continue
        rows = tuple(
            replace(
                row,
                disposition=ImportRowDisposition.IGNORED,
                reason="Duplicate of a normalized row in an earlier selected file.",
                record=None,
            )
            if row.record is not None and row.source_row_number in duplicate_rows
            else row
            for row in file.rows
        )
        result.append(
            replace(
                file,
                records=tuple(kept),
                rows=rows,
                warnings=(
                    *file.warnings,
                    f"{len(duplicate_rows)} overlapping normalized row(s) were ignored.",
                ),
            )
        )
    return tuple(result)


def _validate_single_broker(files: tuple[ParsedCsvFile, ...]) -> None:
    brokers = {
        file.detected_broker for file in files if file.detected_broker is not BrokerKind.GENERIC
    }
    if len(brokers) > 1:
        labels = ", ".join(sorted(broker.value.title() for broker in brokers))
        raise ValueError(
            f"These files match more than one broker ({labels}). "
            "Import each broker as a separate book."
        )


def _dataset_broker(files: tuple[ParsedCsvFile, ...], *, requested: BrokerKind) -> BrokerKind:
    detected = {
        file.detected_broker for file in files if file.detected_broker is not BrokerKind.GENERIC
    }
    return next(iter(detected)) if len(detected) == 1 else requested


def _validate_position_snapshots(files: tuple[ParsedCsvFile, ...]) -> None:
    """Reject incompatible snapshots that would otherwise add the same holding twice."""

    seen: dict[tuple[str, str], Counter[str]] = {}
    for file in files:
        snapshot: dict[tuple[str, str], Counter[str]] = {}
        for record in file.records:
            if record.kind is not ImportRecordKind.POSITION:
                continue
            account = str(record.normalized.get("account_mask") or "...CSV")
            symbol = str(record.normalized.get("symbol") or "").upper()
            identity = (account, symbol)
            snapshot.setdefault(identity, Counter())[record.fingerprint] += 1
        for identity, fingerprints in snapshot.items():
            if sum(fingerprints.values()) > 1:
                account, symbol = identity
                raise ValueError(
                    f"{file.filename} contains more than one position row for {account} {symbol}. "
                    "Use an aggregated position snapshot, not a lot-detail export."
                )
            prior = seen.get(identity)
            if prior is not None and prior != fingerprints:
                account, symbol = identity
                raise ValueError(
                    "Conflicting position snapshots were selected for "
                    f"{account} {symbol}. Import one snapshot for that account and symbol per book."
                )
            seen[identity] = fingerprints
