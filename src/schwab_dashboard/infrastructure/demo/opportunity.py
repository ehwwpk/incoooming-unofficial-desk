from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from schwab_dashboard.domain.instruments import OptionSide
from schwab_dashboard.domain.market import InstrumentRef, QuoteQuality, UnderlyingDailyBar
from schwab_dashboard.domain.opportunity import (
    RadarMarketBundle,
    RadarMarketContract,
    RadarMode,
)
from schwab_dashboard.infrastructure.demo.fixtures.daily_prices import DAILY_CLOSES
from schwab_dashboard.infrastructure.demo.fixtures.holdings import HOLDINGS
from schwab_dashboard.infrastructure.demo.fixtures.open_call_metrics import OPEN_CALL_METRICS
from schwab_dashboard.infrastructure.demo.fixtures.roll_quotes import (
    PUT_ROLL_QUOTE_CANDIDATES,
    ROLL_QUOTE_CANDIDATES,
)
from schwab_dashboard.infrastructure.demo.fixtures.short_puts import PUT_FIXTURES

_SPOTS = {holding.symbol: holding.current_price for holding in HOLDINGS}


class DemoOpportunityMarketGateway:
    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))

    def fetch(
        self,
        *,
        symbol: str,
        mode: RadarMode,
        from_date: date,
        to_date: date,
    ) -> RadarMarketBundle:
        spot = _SPOTS.get(symbol)
        if spot is None:
            raise LookupError("The demo Radar supports CVX, KTOS, and URNM.")
        now = self._clock()
        side = mode.option_side
        expirations = _listed_fridays(from_date, to_date)
        strikes = _listed_strikes(symbol, spot, side)
        contracts = tuple(
            _contract(
                symbol=symbol,
                spot=spot,
                side=side,
                expiration=expiration,
                strike=strike,
                index=week_index * len(strikes) + strike_index + 1,
                now=now,
            )
            for week_index, expiration in enumerate(expirations)
            for strike_index, strike in enumerate(strikes)
        )
        return RadarMarketBundle(
            source="demo",
            symbol=symbol,
            observed_at=now,
            underlying_price=spot,
            contracts=_bound_generated_quotes(contracts),
            daily_bars=_daily_bars(symbol=symbol, spot=spot, as_of=now.date()),
            capabilities=("option_chain", "greeks", "daily_bars"),
            warnings=(
                "Fictional Radar quotes for interface evaluation only.",
                "Daily closes reuse the frozen demo tape; "
                "OHLC envelopes and volume are illustrative.",
            ),
        )


def _listed_fridays(from_date: date, to_date: date) -> tuple[date, ...]:
    end = to_date if to_date > from_date else from_date + timedelta(days=56)
    first = from_date + timedelta(days=(4 - from_date.weekday()) % 7)
    expiries = []
    current = first
    while current <= end:
        expiries.append(current)
        current += timedelta(days=7)
    while len(expiries) < 3:
        last = expiries[-1] if expiries else first
        nxt = last + timedelta(days=7) if expiries else first
        expiries.append(nxt)
    return tuple(expiries)


def _listed_strikes(symbol: str, spot: Decimal, side: OptionSide) -> tuple[Decimal, ...]:
    atm = _rounded_strike(spot)
    step = Decimal("5")
    direction = Decimal("1") if side is OptionSide.CALL else Decimal("-1")
    strikes = {atm + direction * step * offset for offset in range(4)}
    fixtures = ROLL_QUOTE_CANDIDATES if side is OptionSide.CALL else PUT_ROLL_QUOTE_CANDIDATES
    for (underlying, _, source_strike), quotes in fixtures.items():
        if underlying == symbol:
            strikes.add(source_strike)
            strikes.update(quote.strike for quote in quotes)
    return tuple(
        sorted((strike for strike in strikes if strike > 0), reverse=side is OptionSide.PUT)
    )


def _contract(
    *,
    symbol: str,
    spot: Decimal,
    side: OptionSide,
    expiration: date,
    strike: Decimal,
    index: int,
    now: datetime,
) -> RadarMarketContract:
    distance = abs(strike - spot) / spot
    bid = max(Decimal("0.18"), spot * (Decimal("0.018") - distance * Decimal("0.04")))
    ask = bid + max(Decimal("0.05"), bid * Decimal("0.08"))
    side_letter = "C" if side is OptionSide.CALL else "P"
    # A synthetic moneyness curve keeps call/put signs and bounds coherent at
    # every expiration; a chain row index must not change the side of delta.
    call_delta = min(
        Decimal("0.95"), max(Decimal("0.05"), Decimal("0.5") + (spot - strike) / spot * 3)
    )
    contract = RadarMarketContract(
        option_symbol=f"{symbol}-{expiration.isoformat()}-{side_letter}-{strike}",
        underlying_symbol=symbol,
        option_side=side,
        expiration_date=expiration,
        strike=strike,
        multiplier=Decimal("100"),
        observed_at=now,
        quote_quality=QuoteQuality.COMPLETE,
        bid=bid.quantize(Decimal("0.01")),
        ask=ask.quantize(Decimal("0.01")),
        last=bid,
        mark=(bid + ask) / Decimal("2"),
        underlying_price=spot,
        implied_volatility=Decimal("42") + Decimal(index),
        delta=call_delta if side is OptionSide.CALL else call_delta - Decimal("1"),
        gamma=Decimal("0.02"),
        theta=Decimal("-0.04"),
        vega=Decimal("0.08"),
        volume=40 * index,
        open_interest=250 * index,
    )
    return _with_frozen_quote(contract)


def _with_frozen_quote(contract: RadarMarketContract) -> RadarMarketContract:
    """One frozen quote must follow a contract from the book into Radar."""
    key = (contract.underlying_symbol, contract.expiration_date, contract.strike)
    held = (
        OPEN_CALL_METRICS.get(key)
        if contract.option_side is OptionSide.CALL
        else next(
            (item for item in PUT_FIXTURES if (item.symbol, item.expires_on, item.strike) == key),
            None,
        )
    )
    if held is not None:
        return replace(
            contract,
            bid=held.bid_per_share,
            ask=held.ask_per_share,
            mark=held.mark_per_share,
            last=held.mark_per_share,
            implied_volatility=held.implied_volatility_percent,
            delta=held.delta,
            gamma=held.gamma,
            theta=held.theta_per_share,
            vega=held.vega,
            volume=getattr(held, "volume", contract.volume),
            open_interest=getattr(held, "open_interest", contract.open_interest),
        )
    fixtures = (
        ROLL_QUOTE_CANDIDATES
        if contract.option_side is OptionSide.CALL
        else PUT_ROLL_QUOTE_CANDIDATES
    )
    quote = next(
        (
            quote
            for (symbol, _, _), quotes in fixtures.items()
            if symbol == contract.underlying_symbol
            for quote in quotes
            if quote.expires_on == contract.expiration_date and quote.strike == contract.strike
        ),
        None,
    )
    if quote is None:
        return contract
    bid = quote.sell_bid_per_share
    ask = bid + max(Decimal("0.05"), bid * Decimal("0.08")).quantize(Decimal("0.01"))
    mark = (bid + ask) / Decimal("2")
    return replace(contract, bid=bid, ask=ask, mark=mark, last=mark)


def _bound_generated_quotes(
    contracts: tuple[RadarMarketContract, ...],
) -> tuple[RadarMarketContract, ...]:
    """Keep generated strikes on the correct side of the frozen book quotes.

    These are display fixtures, not a calibrated pricing model. A higher call
    strike must still cost no more, and a higher put strike no less. Preserve
    every held/roll quote so the same contract agrees across the application.
    """
    frozen_keys = {
        *(
            (symbol, expiry, strike, OptionSide.CALL)
            for symbol, expiry, strike in OPEN_CALL_METRICS
        ),
        *((item.symbol, item.expires_on, item.strike, OptionSide.PUT) for item in PUT_FIXTURES),
        *(
            (symbol, quote.expires_on, quote.strike, side)
            for grid, side in (
                (ROLL_QUOTE_CANDIDATES, OptionSide.CALL),
                (PUT_ROLL_QUOTE_CANDIDATES, OptionSide.PUT),
            )
            for (symbol, _, _), quotes in grid.items()
            for quote in quotes
        ),
    }
    anchors = tuple(
        item
        for item in contracts
        if (item.underlying_symbol, item.expiration_date, item.strike, item.option_side)
        in frozen_keys
    )
    result = []
    for item in contracts:
        if item in anchors:
            result.append(item)
            continue
        assert item.bid is not None and item.ask is not None
        bid, ask = item.bid, item.ask
        for anchor in anchors:
            if anchor.expiration_date != item.expiration_date:
                continue
            assert anchor.bid is not None and anchor.ask is not None
            cheaper = (item.strike > anchor.strike) == (item.option_side is OptionSide.CALL)
            bound = min if cheaper else max
            bid, ask = bound(bid, anchor.bid), bound(ask, anchor.ask)
        mark = (bid + ask) / Decimal("2")
        result.append(replace(item, bid=bid, ask=ask, mark=mark, last=mark))
    return tuple(result)


def _daily_bars(
    *,
    symbol: str,
    spot: Decimal,
    as_of: date,
) -> tuple[UnderlyingDailyBar, ...]:
    frozen_closes = DAILY_CLOSES.get(symbol)
    if frozen_closes is not None:
        prices = tuple(
            (date(2026, int(label[:2]), int(label[3:])), Decimal(close))
            for label, close in frozen_closes
            if date(2026, int(label[:2]), int(label[3:])) <= as_of
        )
    else:
        prices = tuple(
            (
                as_of - timedelta(days=offset),
                spot * (Decimal("0.88") + Decimal(70 - offset) / Decimal("580")),
            )
            for offset in range(70, -1, -1)
        )
    bars = []
    for trade_date, price in prices:
        bars.append(
            UnderlyingDailyBar(
                instrument=InstrumentRef(source="demo", external_key=f"market:{symbol}"),
                trade_date=trade_date,
                open=price * Decimal("0.995"),
                high=price * Decimal("1.012"),
                low=price * Decimal("0.988"),
                close=price,
                volume=1_000_000,
            )
        )
    return tuple(bars)


def _rounded_strike(value: Decimal) -> Decimal:
    return (value / Decimal("5")).quantize(Decimal("1")) * Decimal("5")
