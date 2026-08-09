from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from schwab_dashboard.domain.validation import require_aware, require_text


class ValueStatus(StrEnum):
    OBSERVED = "observed"
    DERIVED = "derived"
    ESTIMATED = "estimated"
    SIMULATED = "simulated"


class DataQuality(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    STALE = "stale"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class CalculationContext:
    as_of: datetime
    status: ValueStatus
    method: str
    method_version: str
    source_ids: tuple[str, ...]
    quality: DataQuality = DataQuality.COMPLETE

    def __post_init__(self) -> None:
        require_aware(self.as_of, "as_of")
        require_text(self.method, "method")
        require_text(self.method_version, "method_version")
        if not self.source_ids:
            raise ValueError("source_ids must identify at least one input")
        for source_id in self.source_ids:
            require_text(source_id, "source_id")
