from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
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
class RollScenario:
    """Quote-based roll comparison; context only, never an order instruction."""

    target_expiration: date
    target_strike: Decimal
    strike_lift_per_share: Decimal
    added_days: int
    net_roll_per_share: Decimal
    net_roll_cash: Decimal
    assignment_room_gain: Decimal
    target_buffer_percent: Decimal
    quote_source: str


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
    roll_scenarios: tuple[RollScenario, ...] = ()
