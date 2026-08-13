from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from schwab_dashboard.application.imports import parse_csv_file
from schwab_dashboard.application.ports.source_store import SourceDatasetStore
from schwab_dashboard.domain.data_source import BrokerKind, SourceDataset


class ImportCsvDataset:
    def __init__(self, *, store: SourceDatasetStore) -> None:
        self._store = store

    def execute(
        self,
        *,
        name: str,
        broker: BrokerKind,
        files: Sequence[tuple[str, bytes]],
    ) -> SourceDataset:
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
            parse_csv_file(filename=filename, content=content)
            for filename, content in files
        )
        hashes = [item.sha256 for item in parsed]
        if len(hashes) != len(set(hashes)):
            raise ValueError("The same CSV file was selected more than once.")
        return self._store.create_dataset(
            name=clean_name,
            broker=broker,
            files=parsed,
            created_at=datetime.now(UTC),
        )
