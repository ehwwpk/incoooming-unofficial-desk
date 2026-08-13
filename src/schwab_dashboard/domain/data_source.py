from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from schwab_dashboard.domain.validation import require_aware, require_text


class BrokerKind(StrEnum):
    SCHWAB = "schwab"
    FIDELITY = "fidelity"
    ROBINHOOD = "robinhood"
    WEBULL = "webull"
    IBKR = "ibkr"
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


class ImportRowDisposition(StrEnum):
    IMPORTED = "imported"
    IGNORED = "ignored"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"


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
    ignored_count: int
    review_count: int
    rejected_count: int
    capabilities: tuple[str, ...]
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
                self.ignored_count,
                self.review_count,
                self.rejected_count,
            )
            < 0
        ):
            raise ValueError("dataset counts must be non-negative")


@dataclass(frozen=True, slots=True)
class ParsedImportRecord:
    kind: ImportRecordKind
    external_key: str
    fingerprint: str
    source_row_number: int
    normalized: dict[str, object]
    raw: dict[str, str]


@dataclass(frozen=True, slots=True)
class ParsedImportRow:
    source_row_number: int
    disposition: ImportRowDisposition
    raw: dict[str, str]
    reason: str | None = None
    record: ParsedImportRecord | None = None


@dataclass(frozen=True, slots=True)
class ParsedCsvFile:
    filename: str
    file_kind: str
    headers: tuple[str, ...]
    records: tuple[ParsedImportRecord, ...]
    rows: tuple[ParsedImportRow, ...]
    warnings: tuple[str, ...]
    sha256: str
    detected_broker: BrokerKind
    profile: str
    confidence: str
    header_row: int
    encoding: str
    delimiter: str
    capabilities: tuple[str, ...]

    @property
    def imported_count(self) -> int:
        return len(self.records)

    @property
    def ignored_count(self) -> int:
        return sum(row.disposition is ImportRowDisposition.IGNORED for row in self.rows)

    @property
    def review_count(self) -> int:
        return sum(row.disposition is ImportRowDisposition.NEEDS_REVIEW for row in self.rows)

    @property
    def rejected_count(self) -> int:
        return sum(row.disposition is ImportRowDisposition.REJECTED for row in self.rows)


@dataclass(frozen=True, slots=True)
class CsvImportPreview:
    name: str
    requested_broker: BrokerKind
    fingerprint: str
    files: tuple[ParsedCsvFile, ...]
    position_count: int
    activity_count: int
    ignored_count: int
    review_count: int
    rejected_count: int
    capabilities: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def can_commit(self) -> bool:
        return bool(self.position_count or self.activity_count)
