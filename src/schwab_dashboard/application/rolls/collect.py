from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

from schwab_dashboard.application.rolls.models import RollQuote
from schwab_dashboard.domain.instruments import OptionSide

ZERO = Decimal("0")
HUNDRED = Decimal("100")


def collect_roll_quotes(
    *,
    underlying_symbol: str,
    option_side: OptionSide | str,
    source_expiration: date,
    source_strike: Decimal,
    source_option_symbol: str = "",
    option_market: Sequence[Mapping[str, object]] = (),
) -> tuple[RollQuote, ...]:
    """Pull later, directionally valid replacement quotes from a loaded chain."""

    side = _side(option_side)
    source_key = _canonical(source_option_symbol)
    best: dict[str, RollQuote] = {}
    for row in option_market:
        if _canonical(str(row.get("underlying_symbol") or "")) != _canonical(underlying_symbol):
            continue
        try:
            row_side = _side(str(row.get("option_side") or ""))
        except ValueError:
            continue
        if row_side is not side:
            continue
        expiration = _date(row.get("expiration_date"))
        strike = _decimal(row.get("strike"))
        bid = _decimal(row.get("bid"))
        symbol = str(row.get("symbol") or "")
        if expiration is None or expiration <= source_expiration or bid <= ZERO:
            continue
        if side is OptionSide.CALL and strike <= source_strike:
            continue
        if side is OptionSide.PUT and strike > source_strike:
            continue
        if source_key and _canonical(symbol) == source_key:
            continue
        ask = _optional_decimal(row.get("ask"))
        mark = _optional_decimal(row.get("mark"))
        spread = max(ZERO, (ask or bid) - bid)
        quality = str(row.get("quote_quality") or "observed").replace("_", " ").upper()
        quote = RollQuote(
            option_symbol=symbol,
            expires_on=expiration,
            strike=strike,
            sell_bid_per_share=bid,
            quote_source=f"SCHWAB CHAIN · {quality} BID",
            spread_percent=(spread / mark * HUNDRED if mark else None),
            open_interest=_optional_int(row.get("open_interest")),
            volume=_optional_int(row.get("volume")),
            theta_per_share=_optional_decimal(row.get("theta")),
            quote_observed_at=_datetime(row.get("observed_at")),
        )
        key = _canonical(symbol) or f"{expiration.isoformat()}:{strike}"
        current = best.get(key)
        if current is None or _quote_rank(quote) < _quote_rank(current):
            best[key] = quote
    return tuple(sorted(best.values(), key=lambda item: (item.expires_on, item.strike)))


def _quote_rank(quote: RollQuote) -> tuple[object, ...]:
    liquidity = (quote.open_interest or 0) + (quote.volume or 0)
    spread = quote.spread_percent if quote.spread_percent is not None else Decimal("999")
    return (-_epoch(quote.quote_observed_at), spread, -liquidity, quote.option_symbol)


def _epoch(value: datetime | None) -> float:
    if value is None:
        return 0.0
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC).timestamp()
    return value.timestamp()


def _side(value: OptionSide | str) -> OptionSide:
    if isinstance(value, OptionSide):
        return value
    normalized = str(value or "").strip().upper()
    if normalized in {"CALL", "C"}:
        return OptionSide.CALL
    if normalized in {"PUT", "P"}:
        return OptionSide.PUT
    raise ValueError(f"Unsupported option side: {value!r}")


def _canonical(value: str) -> str:
    return "".join(value.upper().split())


def _decimal(value: object) -> Decimal:
    if value is None or value == "":
        return ZERO
    return Decimal(str(value))


def _optional_decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(str(value))


def _date(value: object) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    return None
