from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from schwab_dashboard.domain.validation import require_aware, require_text


class BrokerKind(StrEnum):
    SCHWAB = "schwab"
    FIDELITY = "fidelity"
    ROBINHOOD = "robinhood"
    GENERIC = "generic"


class ImportRecordKind(StrEnum):
    POSITION = "position"
    EXECUTION = "execution"
    CASH_MOVEMENT = "cash_movement"
    LIFECYCLE = "lifecycle"


class DatasetState(StrEnum):
    READY = "ready"
    PARTIAL = "partial"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class SourceDataset:
    id: str
    name: str
    broker: BrokerKind
    state: DatasetState
    created_at: datetime
    file_count: int
    position_count: int
    activity_count: int
    rejected_count: int
    warnings: tuple[str, ...]

    def __post_init__(self) -> None:
        require_text(self.id, "id")
        require_text(self.name, "name")
        require_aware(self.created_at, "created_at")
        if (
            min(
                self.file_count,
                self.position_count,
                self.activity_count,
                self.rejected_count,
            )
            < 0
        ):
            raise ValueError("dataset counts must be non-negative")


@dataclass(frozen=True, slots=True)
class ParsedImportRecord:
    kind: ImportRecordKind
    external_key: str
    normalized: dict[str, object]
    raw: dict[str, str]


@dataclass(frozen=True, slots=True)
class ParsedCsvFile:
    filename: str
    file_kind: str
    headers: tuple[str, ...]
    records: tuple[ParsedImportRecord, ...]
    rejected_count: int
    warnings: tuple[str, ...]
    sha256: str
