from decimal import Decimal


def compact_decimal(value: Decimal) -> str:
    """Render a broker Decimal without database scale padding or exponent notation."""

    return format(value.normalize(), "f")
