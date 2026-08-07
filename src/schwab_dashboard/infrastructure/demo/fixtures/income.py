from decimal import Decimal

from schwab_dashboard.application.dashboard.models import IncomePeriod

D = Decimal


def build_income_periods() -> tuple[IncomePeriod, ...]:
    rows = (
        ("May 15", "1155", "0"),
        ("May 22", "660", "0"),
        ("May 29", "580", "0"),
        ("Jun 05", "260", "0"),
        ("Jun 12", "0", "1246"),
        ("Jun 19", "0", "0"),
        ("Jun 26", "2110", "0"),
        ("Jul 03", "-160", "0"),
        ("Jul 10", "720", "0"),
        ("Jul 17", "0", "0"),
        ("Jul 24", "360", "0"),
        ("Jul 31", "760", "0"),
        ("Aug 07", "-105", "0"),
    )
    maximum = max(abs(D(option_income) + D(dividends)) for _, option_income, dividends in rows)
    return tuple(
        _period(label, D(option_income), D(dividends), maximum)
        for label, option_income, dividends in rows
    )


def _period(
    label: str,
    option_income: Decimal,
    dividends: Decimal,
    maximum: Decimal,
) -> IncomePeriod:
    total = option_income + dividends
    return IncomePeriod(
        label=label,
        option_income=option_income,
        dividends=dividends,
        total=total,
        bar_percent=(0 if not total else max(8, int(abs(total) / maximum * 100))),
    )
