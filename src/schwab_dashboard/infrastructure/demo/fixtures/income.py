from decimal import Decimal

from schwab_dashboard.application.dashboard.models import IncomePeriod

D = Decimal


def build_income_periods() -> tuple[IncomePeriod, ...]:
    rows = (
        ("Jun 19", "810.00", "0", 54),
        ("Jun 26", "1240.00", "184.00", 94),
        ("Jul 03", "930.00", "0", 62),
        ("Jul 10", "1510.00", "0", 100),
        ("Jul 17", "875.00", "335.00", 80),
        ("Jul 24", "1320.00", "0", 87),
        ("Jul 31", "1175.00", "0", 78),
        ("Aug 07", "1095.00", "153.50", 83),
    )
    return tuple(
        IncomePeriod(
            label=label,
            option_income=D(option_income),
            dividends=D(dividends),
            total=D(option_income) + D(dividends),
            bar_percent=bar_percent,
        )
        for label, option_income, dividends, bar_percent in rows
    )
