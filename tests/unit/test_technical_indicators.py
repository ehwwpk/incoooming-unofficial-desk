from datetime import date, timedelta
from decimal import Decimal

from schwab_dashboard.application.opportunities.technical_indicators import (
    calculate_daily_indicators,
)
from schwab_dashboard.domain.market import InstrumentRef, UnderlyingDailyBar


def test_rsi_uses_a_real_fourteen_change_warmup_and_wilder_smoothing() -> None:
    values = tuple(Decimal(index) for index in range(1, 22))
    result = calculate_daily_indicators(_bars(values))

    assert all(point.rsi_14 is None for point in result[:14])
    assert all(point.rsi_14 == Decimal("100") for point in result[14:])


def test_flat_history_reports_neutral_rsi_instead_of_dividing_by_zero() -> None:
    result = calculate_daily_indicators(_bars((Decimal("50"),) * 20))

    assert result[14].rsi_14 == Decimal("50")
    assert result[-1].rsi_14 == Decimal("50")


def test_macd_waits_for_slow_and_signal_warmups() -> None:
    values = tuple(Decimal(index) for index in range(1, 61))
    result = calculate_daily_indicators(_bars(values))

    assert all(point.macd is None for point in result[:25])
    assert result[25].macd is not None
    assert all(point.macd_signal is None for point in result[:33])
    assert result[33].macd_signal is not None
    assert result[33].macd_histogram is not None
    assert result[-1].macd is not None and result[-1].macd > 0


def test_short_history_returns_explicitly_unavailable_indicators() -> None:
    result = calculate_daily_indicators(_bars((Decimal("10"),) * 10))

    assert result
    assert all(point.rsi_14 is None for point in result)
    assert all(point.macd is None for point in result)
    assert all(point.macd_signal is None for point in result)


def _bars(values: tuple[Decimal, ...]) -> tuple[UnderlyingDailyBar, ...]:
    start = date(2026, 1, 2)
    instrument = InstrumentRef(source="test", external_key="market:TEST")
    return tuple(
        UnderlyingDailyBar(
            instrument=instrument,
            trade_date=start + timedelta(days=index),
            open=value,
            high=value,
            low=value,
            close=value,
            volume=1000,
        )
        for index, value in enumerate(values)
    )
