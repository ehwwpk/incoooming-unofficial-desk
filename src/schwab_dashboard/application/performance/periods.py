from __future__ import annotations

from calendar import monthrange
from datetime import date
from enum import StrEnum


class PerformancePeriod(StrEnum):
    ALL = "all"
    ONE_YEAR = "1y"
    SIX_MONTHS = "6m"
    THREE_MONTHS = "3m"
    ONE_MONTH = "1m"

    @property
    def label(self) -> str:
        return {
            self.ALL: "ALL",
            self.ONE_YEAR: "1Y",
            self.SIX_MONTHS: "6M",
            self.THREE_MONTHS: "3M",
            self.ONE_MONTH: "1M",
        }[self]

    def starts_on(self, *, through: date) -> date | None:
        months = {
            self.ALL: None,
            self.ONE_YEAR: 12,
            self.SIX_MONTHS: 6,
            self.THREE_MONTHS: 3,
            self.ONE_MONTH: 1,
        }[self]
        return None if months is None else _subtract_months(through, months)


# Present time windows from the tightest review to the broadest history.  The
# enum order is deliberately not used here: URL parsing is independent of the
# way the selector should read to a person.
PERFORMANCE_PERIODS = (
    PerformancePeriod.ONE_MONTH,
    PerformancePeriod.THREE_MONTHS,
    PerformancePeriod.SIX_MONTHS,
    PerformancePeriod.ONE_YEAR,
    PerformancePeriod.ALL,
)


def _subtract_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 - months
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)
