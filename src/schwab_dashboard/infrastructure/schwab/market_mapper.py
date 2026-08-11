from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from schwab_dashboard.domain.instruments import (
    AssetType,
    DeliverableComponent,
    DeliverableKind,
    InstrumentRecord,
    OptionDeliverable,
    OptionSide,
)
from schwab_dashboard.domain.market import (
    InstrumentRef,
    MarketObservationBatch,
    MarkMethod,
    OptionMarketSnapshot,
    QuoteQuality,
    UnderlyingDailyBar,
    UnderlyingMarketSnapshot,
)
from schwab_dashboard.infrastructure.schwab.option_symbol import parse_occ_option_symbol

ZERO = Decimal("0")
INVALID_MARKET_SENTINEL = Decimal("-900")


class SchwabMarketMapper:
    def map_quotes(
        self,
        payload: Mapping[str, Any],
        *,
        observed_at: datetime,
        parser_version: str,
    ) -> MarketObservationBatch:
        instruments: list[InstrumentRecord] = []
        snapshots: list[UnderlyingMarketSnapshot] = []
        for symbol, row in payload.items():
            if not isinstance(row, Mapping):
                continue
            quote = _mapping(row.get("quote"))
            if not quote:
                continue
            normalized_symbol = str(row.get("symbol") or symbol).strip()
            external_key = f"market:{normalized_symbol}"
            timestamp = _epoch_millis(quote.get("quoteTime"), fallback=observed_at)
            bid = _market_decimal(quote.get("bidPrice"))
            ask = _market_decimal(quote.get("askPrice"))
            last = _market_decimal(quote.get("lastPrice"))
            mark = _market_decimal(quote.get("mark"))
            instruments.append(
                InstrumentRecord(
                    source="schwab",
                    external_key=external_key,
                    symbol=normalized_symbol,
                    asset_type=_quote_asset_type(row),
                    observed_at=observed_at,
                    description=_optional_text(_mapping(row.get("reference")).get("description")),
                )
            )
            snapshots.append(
                UnderlyingMarketSnapshot(
                    instrument=InstrumentRef(source="schwab", external_key=external_key),
                    observed_at=timestamp,
                    quote_quality=_quote_quality(bid, ask),
                    mark_method=_mark_method(mark, bid, ask, last),
                    bid=bid,
                    ask=ask,
                    last=last,
                    mark=mark or _midpoint(bid, ask) or last,
                    previous_close=_market_decimal(quote.get("closePrice")),
                )
            )
        return MarketObservationBatch(
            source="schwab",
            external_event_key=f"quotes:{observed_at.isoformat()}",
            observed_at=observed_at,
            parser_version=parser_version,
            raw_payload=dict(payload),
            instruments=tuple(instruments),
            underlying_snapshots=tuple(snapshots),
        )

    def map_chain(
        self,
        payload: Mapping[str, Any],
        *,
        observed_at: datetime,
        parser_version: str,
        open_option_symbols: Sequence[str],
    ) -> MarketObservationBatch:
        requested = {_canonical_symbol(symbol) for symbol in open_option_symbols}
        underlying_symbol = str(payload.get("symbol") or "").strip()
        underlying_price = _market_decimal(payload.get("underlyingPrice"))
        instruments: list[InstrumentRecord] = []
        snapshots: list[OptionMarketSnapshot] = []
        for contract in _chain_contracts(payload.get("callExpDateMap")):
            symbol = _optional_text(contract.get("symbol"))
            if not symbol or _canonical_symbol(symbol) not in requested:
                continue
            parsed = parse_occ_option_symbol(symbol)
            if parsed is None:
                continue
            external_key = f"market:{symbol}"
            multiplier = _market_decimal(contract.get("multiplier")) or Decimal("100")
            bid = _market_decimal(contract.get("bid"))
            ask = _market_decimal(contract.get("ask"))
            last = _market_decimal(contract.get("last"))
            mark = _market_decimal(contract.get("mark"))
            instruments.append(
                InstrumentRecord(
                    source="schwab",
                    external_key=external_key,
                    symbol=symbol,
                    asset_type=AssetType.OPTION,
                    observed_at=observed_at,
                    description=_optional_text(contract.get("description")),
                    underlying_symbol=underlying_symbol or parsed.underlying_symbol,
                    option_side=OptionSide.CALL,
                    expiration_date=parsed.expiration_date,
                    strike=_market_decimal(contract.get("strikePrice")) or parsed.strike,
                    contract_multiplier=multiplier,
                    deliverable=OptionDeliverable(
                        kind=(
                            DeliverableKind.ADJUSTED
                            if bool(contract.get("nonStandard"))
                            else DeliverableKind.STANDARD
                        ),
                        components=(
                            DeliverableComponent(
                                asset_type=AssetType.EQUITY,
                                symbol=underlying_symbol or parsed.underlying_symbol,
                                quantity=multiplier,
                            ),
                        ),
                    ),
                )
            )
            snapshots.append(
                OptionMarketSnapshot(
                    instrument=InstrumentRef(source="schwab", external_key=external_key),
                    observed_at=_epoch_millis(
                        contract.get("quoteTimeInLong"), fallback=observed_at
                    ),
                    quote_quality=_quote_quality(bid, ask),
                    mark_method=_mark_method(mark, bid, ask, last),
                    bid=bid,
                    ask=ask,
                    last=last,
                    mark=mark or _midpoint(bid, ask) or last,
                    underlying_price=underlying_price,
                    implied_volatility=_market_decimal(contract.get("volatility")),
                    delta=_greek(contract.get("delta")),
                    gamma=_greek(contract.get("gamma")),
                    theta=_greek(contract.get("theta")),
                    vega=_greek(contract.get("vega")),
                    rho=_greek(contract.get("rho")),
                    volume=_optional_int(contract.get("totalVolume")),
                    open_interest=_optional_int(contract.get("openInterest")),
                )
            )
        return MarketObservationBatch(
            source="schwab",
            external_event_key=f"chain:{underlying_symbol}:{observed_at.isoformat()}",
            observed_at=observed_at,
            parser_version=parser_version,
            raw_payload=dict(payload),
            instruments=tuple(instruments),
            option_snapshots=tuple(snapshots),
        )

    def map_price_history(
        self,
        payload: Mapping[str, Any],
        *,
        observed_at: datetime,
        parser_version: str,
    ) -> MarketObservationBatch:
        symbol = str(payload.get("symbol") or "").strip()
        if not symbol:
            raise ValueError("Schwab price history is missing its symbol")
        external_key = f"market:{symbol}"
        bars: list[UnderlyingDailyBar] = []
        raw_candles = payload.get("candles") or []
        if not isinstance(raw_candles, Sequence) or isinstance(raw_candles, (str, bytes)):
            raise ValueError("Schwab price history candles are not a list")
        for candle in raw_candles:
            if not isinstance(candle, Mapping):
                continue
            timestamp = _epoch_millis(candle.get("datetime"), fallback=observed_at)
            bars.append(
                UnderlyingDailyBar(
                    instrument=InstrumentRef(source="schwab", external_key=external_key),
                    trade_date=timestamp.date(),
                    open=_required_market_decimal(candle.get("open")),
                    high=_required_market_decimal(candle.get("high")),
                    low=_required_market_decimal(candle.get("low")),
                    close=_required_market_decimal(candle.get("close")),
                    volume=_optional_int(candle.get("volume")) or 0,
                )
            )
        return MarketObservationBatch(
            source="schwab",
            external_event_key=f"history:{symbol}:{observed_at.isoformat()}",
            observed_at=observed_at,
            parser_version=parser_version,
            raw_payload=dict(payload),
            instruments=(
                InstrumentRecord(
                    source="schwab",
                    external_key=external_key,
                    symbol=symbol,
                    asset_type=AssetType.EQUITY,
                    observed_at=observed_at,
                ),
            ),
            daily_bars=tuple(bars),
        )


def _chain_contracts(value: Any) -> tuple[Mapping[str, Any], ...]:
    contracts: list[Mapping[str, Any]] = []
    if not isinstance(value, Mapping):
        return ()
    for strike_map in value.values():
        if not isinstance(strike_map, Mapping):
            continue
        for rows in strike_map.values():
            if isinstance(rows, Sequence) and not isinstance(rows, (str, bytes)):
                contracts.extend(row for row in rows if isinstance(row, Mapping))
    return tuple(contracts)


def _quote_asset_type(row: Mapping[str, Any]) -> AssetType:
    main = str(row.get("assetMainType") or "").upper()
    subtype = str(row.get("assetSubType") or "").upper()
    if main == "EQUITY" and subtype == "ETF":
        return AssetType.ETF
    if main == "EQUITY":
        return AssetType.EQUITY
    return AssetType.UNKNOWN


def _quote_quality(bid: Decimal | None, ask: Decimal | None) -> QuoteQuality:
    if bid is not None and ask is not None:
        return QuoteQuality.CROSSED if bid > ask else QuoteQuality.COMPLETE
    if bid is not None or ask is not None:
        return QuoteQuality.ONE_SIDED
    return QuoteQuality.NO_MARKET


def _mark_method(
    mark: Decimal | None,
    bid: Decimal | None,
    ask: Decimal | None,
    last: Decimal | None,
) -> MarkMethod:
    if mark is not None:
        return MarkMethod.BROKER
    if _midpoint(bid, ask) is not None:
        return MarkMethod.MIDPOINT
    if last is not None:
        return MarkMethod.LAST
    return MarkMethod.UNAVAILABLE


def _midpoint(bid: Decimal | None, ask: Decimal | None) -> Decimal | None:
    if bid is None or ask is None or bid > ask:
        return None
    return (bid + ask) / Decimal("2")


def _greek(value: Any) -> Decimal | None:
    parsed = _optional_decimal(value)
    return None if parsed is not None and parsed <= INVALID_MARKET_SENTINEL else parsed


def _market_decimal(value: Any) -> Decimal | None:
    parsed = _optional_decimal(value)
    return None if parsed is not None and parsed < ZERO else parsed


def _required_market_decimal(value: Any) -> Decimal:
    parsed = _market_decimal(value)
    if parsed is None:
        raise ValueError("Schwab market payload contains a missing or invalid price")
    return parsed


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Schwab market payload contains a non-numeric value") from exc


def _optional_int(value: Any) -> int | None:
    parsed = _optional_decimal(value)
    return int(parsed) if parsed is not None and parsed >= ZERO else None


def _epoch_millis(value: Any, *, fallback: datetime) -> datetime:
    if value is None:
        return fallback
    try:
        return datetime.fromtimestamp(float(value) / 1000, tz=UTC)
    except (TypeError, ValueError, OSError) as exc:
        raise ValueError("Schwab market timestamp is invalid") from exc


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _optional_text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _canonical_symbol(value: str) -> str:
    return "".join(value.upper().split())
