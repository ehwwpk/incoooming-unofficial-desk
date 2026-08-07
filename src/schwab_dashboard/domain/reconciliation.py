from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class IssueSeverity(StrEnum):
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class ReconciliationIssue:
    code: str
    severity: IssueSeverity
    message: str
    account_external_key: str
    instrument_key: str | None = None
    context: dict[str, Any] = field(default_factory=dict)
