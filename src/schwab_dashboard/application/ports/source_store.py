from __future__ import annotations

from datetime import datetime
from typing import Protocol

from schwab_dashboard.domain.data_source import (
    BrokerKind,
    ParsedCsvFile,
    SourceDataset,
)


class SourceDatasetStore(Protocol):
    def create_dataset(
        self,
        *,
        name: str,
        broker: BrokerKind,
        files: tuple[ParsedCsvFile, ...],
        created_at: datetime,
    ) -> SourceDataset: ...

    def list_datasets(self) -> tuple[SourceDataset, ...]: ...

    def get_dataset(self, dataset_id: str) -> SourceDataset | None: ...

    def load_records(self, dataset_id: str) -> tuple[dict[str, object], ...]: ...
