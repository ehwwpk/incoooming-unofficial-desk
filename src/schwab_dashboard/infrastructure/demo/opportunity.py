from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from schwab_dashboard.domain.instruments import OptionSide
from schwab_dashboard.domain.market import InstrumentRef, QuoteQuality, UnderlyingDailyBar
from schwab_dashboard.domain.opportunity import (
    RadarMarketBundle,
    RadarMarketContract,
    RadarMode,
)

_SPOTS = {
    "CVX": Decimal("196.66"),
    "KTOS": Decimal("63.73"),
    "URNM": Decimal("55.37"),
}


class DemoOpportunityMarketGateway:
    def fetch(
        self,
        *,
        symbol: str,
        mode: RadarMode,
        from_date: date,
        to_date: date,
    ) -> RadarMarketBundle:
        del from_date, to_date
        spot = _SPOTS.get(symbol)
        if spot is None:
            raise LookupError("The demo Radar supports CVX, KTOS, and URNM.")
        now = datetime.now(UTC)
        side = mode.option_side
        expirations = (
            now.date() + timedelta(days=21),
            now.date() + timedelta(days=35),
            now.date() + timedelta(days=56),
        )
        ratios = (
            (Decimal("1.10"), Decimal("1.18"), Decimal("1.28"))
            if side is OptionSide.CALL
            else (Decimal("0.95"), Decimal("0.90"), Decimal("0.84"))
        )
        contracts = tuple(
            _contract(
                symbol=symbol,
                spot=spot,
                side=side,
                expiration=expiration,
                strike=_rounded_strike(spot * ratio),
                index=index,
                now=now,
            )
            for index, (expiration, ratio) in enumerate(
                zip(expirations, ratios, strict=True), start=1
            )
        )
        return RadarMarketBundle(
            source="demo",
            symbol=symbol,
            observed_at=now,
            underlying_price=spot,
            contracts=contracts,
            daily_bars=_daily_bars(symbol=symbol, spot=spot, as_of=now.date()),
            capabilities=("option_chain", "greeks", "daily_bars"),
            warnings=("Fictional Radar quotes for interface evaluation only.",),
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
    ask = bid * (Decimal("1.08") + Decimal(index) * Decimal("0.015"))
    side_letter = "C" if side is OptionSide.CALL else "P"
    return RadarMarketContract(
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
        implied_volatility=Decimal("42") + Decimal(index * 3),
        delta=(Decimal("0.28") - Decimal(index) * Decimal("0.04"))
        * (Decimal("1") if side is OptionSide.CALL else Decimal("-1")),
        gamma=Decimal("0.02"),
        theta=Decimal("-0.04"),
        vega=Decimal("0.08"),
        volume=40 * index,
        open_interest=250 * index,
    )


def _daily_bars(
    *,
    symbol: str,
    spot: Decimal,
    as_of: date,
) -> tuple[UnderlyingDailyBar, ...]:
    bars = []
    for offset in range(70, -1, -1):
        trade_date = as_of - timedelta(days=offset)
        price = spot * (Decimal("0.88") + Decimal(70 - offset) / Decimal("580"))
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
