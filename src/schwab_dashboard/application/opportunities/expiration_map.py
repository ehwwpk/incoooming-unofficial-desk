from __future__ import annotations

from datetime import date
from decimal import Decimal

from schwab_dashboard.application.opportunities.technical_indicators import (
    calculate_daily_indicators,
)
from schwab_dashboard.domain.opportunity import RadarCandidate, RadarMarketBundle
from schwab_dashboard.domain.opportunity_map import (
    RadarExpirationMap,
    RadarMapAxisLabel,
    RadarMapCandidate,
    RadarMapIndicatorPoint,
    RadarMapPricePoint,
)

_PLOT_LEFT = Decimal("5")
_PLOT_RIGHT = Decimal("88")
_PLOT_TOP = Decimal("7")
_PLOT_BOTTOM = Decimal("89")
_LABEL_GAP = Decimal("7")


def build_expiration_map(
    *,
    bundle: RadarMarketBundle,
    candidates: tuple[RadarCandidate, ...],
    as_of: date,
) -> RadarExpirationMap | None:
    """Project history and contract boundaries onto one auditable price/time plane."""

    spot = bundle.underlying_price
    if spot is None or spot <= 0 or not candidates:
        return None

    all_bars = tuple(
        sorted(
            (bar for bar in bundle.daily_bars if bar.trade_date <= as_of),
            key=lambda bar: bar.trade_date,
        )
    )
    bars = all_bars[-60:]
    indicators_by_date = {item.trade_date: item for item in calculate_daily_indicators(all_bars)}
    history_start = bars[0].trade_date if bars else as_of
    future_end = max(candidate.expiration_date for candidate in candidates)
    if future_end <= history_start:
        future_end = as_of

    observed_prices = [spot]
    for bar in bars:
        observed_prices.extend((bar.low, bar.high, bar.close))
    for candidate in candidates:
        observed_prices.append(candidate.strike)
        if candidate.effective_entry is not None:
            observed_prices.append(candidate.effective_entry)
        if candidate.expected_move is not None:
            observed_prices.extend(
                (
                    max(Decimal("0"), spot - candidate.expected_move),
                    spot + candidate.expected_move,
                )
            )

    raw_minimum = max(Decimal("0"), min(observed_prices))
    raw_maximum = max(observed_prices)
    raw_range = max(raw_maximum - raw_minimum, spot * Decimal("0.05"), Decimal("1"))
    padding = raw_range * Decimal("0.08")
    minimum = max(Decimal("0"), raw_minimum - padding)
    maximum = raw_maximum + padding

    spot_x = _date_x(as_of, start=history_start, end=future_end)
    spot_y = _price_y(spot, minimum=minimum, maximum=maximum)
    points = tuple(
        RadarMapPricePoint(
            trade_date=bar.trade_date,
            close=bar.close,
            x_percent=_date_x(bar.trade_date, start=history_start, end=future_end),
            y_percent=_price_y(bar.close, minimum=minimum, maximum=maximum),
        )
        for bar in bars
    )
    indicator_points = tuple(
        RadarMapIndicatorPoint(
            trade_date=bar.trade_date,
            x_percent=_date_x(bar.trade_date, start=history_start, end=future_end),
            rsi_14=indicators_by_date[bar.trade_date].rsi_14,
            macd=indicators_by_date[bar.trade_date].macd,
            macd_signal=indicators_by_date[bar.trade_date].macd_signal,
            macd_histogram=indicators_by_date[bar.trade_date].macd_histogram,
        )
        for bar in bars
    )

    actual_y = [
        _price_y(candidate.strike, minimum=minimum, maximum=maximum) for candidate in candidates
    ]
    label_y = _spread_labels(actual_y)
    map_candidates = tuple(
        RadarMapCandidate(
            sequence=index,
            option_symbol=candidate.option_symbol,
            strike=candidate.strike,
            expiration_date=candidate.expiration_date,
            days_to_expiration=candidate.days_to_expiration,
            x_percent=_date_x(
                candidate.expiration_date,
                start=history_start,
                end=future_end,
            ),
            y_percent=actual_y[index - 1],
            label_y_percent=label_y[index - 1],
            effective_entry=candidate.effective_entry,
            effective_entry_y_percent=(
                _price_y(candidate.effective_entry, minimum=minimum, maximum=maximum)
                if candidate.effective_entry is not None
                else None
            ),
            expected_move_low=(
                max(Decimal("0"), spot - candidate.expected_move)
                if candidate.expected_move is not None
                else None
            ),
            expected_move_high=(
                spot + candidate.expected_move if candidate.expected_move is not None else None
            ),
            expected_move_low_y_percent=(
                _price_y(
                    max(Decimal("0"), spot - candidate.expected_move),
                    minimum=minimum,
                    maximum=maximum,
                )
                if candidate.expected_move is not None
                else None
            ),
            expected_move_high_y_percent=(
                _price_y(
                    spot + candidate.expected_move,
                    minimum=minimum,
                    maximum=maximum,
                )
                if candidate.expected_move is not None
                else None
            ),
            clears_all_rules=candidate.clears_all_rules,
        )
        for index, candidate in enumerate(candidates, start=1)
    )
    axis_labels = tuple(
        RadarMapAxisLabel(
            price=minimum + (maximum - minimum) * fraction,
            y_percent=_price_y(
                minimum + (maximum - minimum) * fraction,
                minimum=minimum,
                maximum=maximum,
            ),
        )
        for fraction in (Decimal("1"), Decimal("0.6667"), Decimal("0.3333"), Decimal("0"))
    )
    return RadarExpirationMap(
        history_start=history_start,
        as_of=as_of,
        future_end=future_end,
        minimum_price=minimum,
        maximum_price=maximum,
        spot=spot,
        spot_x_percent=spot_x,
        spot_y_percent=spot_y,
        price_points=points,
        indicator_points=indicator_points,
        axis_labels=axis_labels,
        candidates=map_candidates,
    )


def _date_x(value: date, *, start: date, end: date) -> Decimal:
    total_days = max((end - start).days, 1)
    elapsed_days = min(max((value - start).days, 0), total_days)
    return _PLOT_LEFT + (Decimal(elapsed_days) / Decimal(total_days)) * (_PLOT_RIGHT - _PLOT_LEFT)


def _price_y(value: Decimal, *, minimum: Decimal, maximum: Decimal) -> Decimal:
    price_range = max(maximum - minimum, Decimal("0.01"))
    position = (maximum - value) / price_range
    return _PLOT_TOP + position * (_PLOT_BOTTOM - _PLOT_TOP)


def _spread_labels(values: list[Decimal]) -> list[Decimal]:
    """Keep close strikes readable while preserving a connector to the true level."""

    if not values:
        return []
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    placed: list[tuple[int, Decimal]] = []
    cursor = _PLOT_TOP
    for index, value in ordered:
        label = max(value, cursor)
        placed.append((index, label))
        cursor = label + _LABEL_GAP
    overflow = placed[-1][1] - _PLOT_BOTTOM
    if overflow > 0:
        placed = [(index, value - overflow) for index, value in placed]
    underflow = _PLOT_TOP - placed[0][1]
    if underflow > 0:
        placed = [(index, value + underflow) for index, value in placed]
    result = [Decimal("0")] * len(values)
    for index, value in placed:
        result[index] = value
    return result
