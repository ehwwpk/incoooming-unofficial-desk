from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from schwab_dashboard.domain.market import UnderlyingDailyBar


@dataclass(frozen=True, slots=True)
class DailyIndicatorValues:
    trade_date: date
    rsi_14: Decimal | None
    macd: Decimal | None
    macd_signal: Decimal | None
    macd_histogram: Decimal | None


def calculate_daily_indicators(
    bars: tuple[UnderlyingDailyBar, ...],
) -> tuple[DailyIndicatorValues, ...]:
    """Calculate close-based RSI 14 and MACD 12/26/9 without inventing warm-up data."""

    ordered = tuple(sorted(bars, key=lambda bar: bar.trade_date))
    closes = tuple(bar.close for bar in ordered)
    rsi = _wilder_rsi(closes, period=14)
    macd, signal, histogram = _macd(closes, fast_period=12, slow_period=26, signal_period=9)
    return tuple(
        DailyIndicatorValues(
            trade_date=bar.trade_date,
            rsi_14=rsi[index],
            macd=macd[index],
            macd_signal=signal[index],
            macd_histogram=histogram[index],
        )
        for index, bar in enumerate(ordered)
    )


def _wilder_rsi(
    values: tuple[Decimal, ...],
    *,
    period: int,
) -> tuple[Decimal | None, ...]:
    result: list[Decimal | None] = [None] * len(values)
    if len(values) <= period:
        return tuple(result)

    changes = tuple(values[index] - values[index - 1] for index in range(1, len(values)))
    gains = tuple(max(change, Decimal("0")) for change in changes)
    losses = tuple(max(-change, Decimal("0")) for change in changes)
    average_gain = sum(gains[:period], Decimal("0")) / Decimal(period)
    average_loss = sum(losses[:period], Decimal("0")) / Decimal(period)
    result[period] = _rsi_value(average_gain, average_loss)

    for value_index in range(period + 1, len(values)):
        change_index = value_index - 1
        average_gain = (
            average_gain * Decimal(period - 1) + gains[change_index]
        ) / Decimal(period)
        average_loss = (
            average_loss * Decimal(period - 1) + losses[change_index]
        ) / Decimal(period)
        result[value_index] = _rsi_value(average_gain, average_loss)
    return tuple(result)


def _rsi_value(average_gain: Decimal, average_loss: Decimal) -> Decimal:
    if average_loss == 0:
        return Decimal("100") if average_gain > 0 else Decimal("50")
    relative_strength = average_gain / average_loss
    return Decimal("100") - Decimal("100") / (Decimal("1") + relative_strength)


def _macd(
    values: tuple[Decimal, ...],
    *,
    fast_period: int,
    slow_period: int,
    signal_period: int,
) -> tuple[
    tuple[Decimal | None, ...],
    tuple[Decimal | None, ...],
    tuple[Decimal | None, ...],
]:
    fast = _ema(values, period=fast_period)
    slow = _ema(values, period=slow_period)
    macd: list[Decimal | None] = [None] * len(values)
    active_indices: list[int] = []
    active_values: list[Decimal] = []
    for index, (fast_value, slow_value) in enumerate(zip(fast, slow, strict=True)):
        if fast_value is None or slow_value is None:
            continue
        value = fast_value - slow_value
        macd[index] = value
        active_indices.append(index)
        active_values.append(value)

    active_signal = _ema(tuple(active_values), period=signal_period)
    signal: list[Decimal | None] = [None] * len(values)
    histogram: list[Decimal | None] = [None] * len(values)
    for active_index, signal_value in enumerate(active_signal):
        if signal_value is None:
            continue
        source_index = active_indices[active_index]
        signal[source_index] = signal_value
        macd_value = macd[source_index]
        assert macd_value is not None
        histogram[source_index] = macd_value - signal_value
    return tuple(macd), tuple(signal), tuple(histogram)


def _ema(
    values: tuple[Decimal, ...],
    *,
    period: int,
) -> tuple[Decimal | None, ...]:
    result: list[Decimal | None] = [None] * len(values)
    if len(values) < period:
        return tuple(result)

    seed = sum(values[:period], Decimal("0")) / Decimal(period)
    result[period - 1] = seed
    multiplier = Decimal("2") / Decimal(period + 1)
    previous = seed
    for index in range(period, len(values)):
        previous = (values[index] - previous) * multiplier + previous
        result[index] = previous
    return tuple(result)
