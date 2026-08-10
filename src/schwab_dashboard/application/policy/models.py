from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class RetentionIntent(StrEnum):
    PRESERVE = "preserve"
    NEUTRAL = "neutral"
    ACCEPTABLE_EXIT = "acceptable_exit"
    TRIM_REDEPLOY = "trim_redeploy"

    @property
    def label(self) -> str:
        return {
            RetentionIntent.PRESERVE: "PRESERVE SHARES",
            RetentionIntent.NEUTRAL: "NEUTRAL",
            RetentionIntent.ACCEPTABLE_EXIT: "ACCEPTABLE EXIT",
            RetentionIntent.TRIM_REDEPLOY: "TRIM / REDEPLOY",
        }[self]


@dataclass(frozen=True, slots=True)
class CallPolicy:
    policy_id: str
    label: str
    intent: RetentionIntent
    shares: int
    minimum_strike_buffer_percent: Decimal
    minimum_days_to_expiration: int
    maximum_days_to_expiration: int
    acceptable_exit_price: Decimal | None
    avoid_earnings: bool
    avoid_sensitive_dividend_window: bool
    note: str


@dataclass(frozen=True, slots=True)
class UnderlyingPolicy:
    symbol: str
    label: str
    policies: tuple[CallPolicy, ...]

    @property
    def governed_shares(self) -> int:
        return sum(policy.shares for policy in self.policies)


@dataclass(frozen=True, slots=True)
class PolicyFit:
    policy_id: str
    policy_label: str
    intent_label: str
    fits_dte: bool
    fits_strike_buffer: bool
    acceptable_exit: bool | None
    passed_checks: int
    total_checks: int
    summary: str

    @property
    def fits(self) -> bool:
        return self.passed_checks == self.total_checks
