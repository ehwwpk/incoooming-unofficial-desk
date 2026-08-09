from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AlertLevel(StrEnum):
    ATTENTION = "attention"
    CHECK = "check"
    WATCH = "watch"

    @property
    def friendly_label(self) -> str:
        return {
            AlertLevel.ATTENTION: "NEEDS ATTENTION",
            AlertLevel.CHECK: "WORTH CHECKING",
            AlertLevel.WATCH: "KEEP AN EYE ON THIS",
        }[self]


@dataclass(frozen=True, slots=True)
class AlertFact:
    label: str
    value: str
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class DeskAlert:
    alert_id: str
    reason_code: str
    level: AlertLevel
    level_label: str
    symbol: str
    target_id: str
    headline: str
    message: str
    facts: tuple[AlertFact, ...]
    priority: int
    method_note: str | None = None
