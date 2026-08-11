from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal

from schwab_dashboard.application.dashboard.covered_calls import (
    OpenCallClock,
    RollQuoteCandidate,
)
from schwab_dashboard.application.dashboard.models import LiveOpenOptionPosition

ZERO = Decimal("0")
HUNDRED = Decimal("100")
CONTRACT_MULTIPLIER = Decimal("100")


def build_open_call_clocks(
    symbol: str,
    calls: Sequence[LiveOpenOptionPosition],
    *,
    executions: Sequence[Mapping[str, object]],
    daily_bars: Sequence[Mapping[str, object]],
    option_market: Sequence[Mapping[str, object]] = (),
    as_of: date,
) -> tuple[OpenCallClock, ...]:
    return tuple(
        _clock(
            call,
            opening_rows=_remaining_opening_rows(call.option_symbol, executions),
            daily_bars=daily_bars,
            option_market=option_market,
            as_of=as_of,
        )
        for call in calls
        if call.underlying_symbol == symbol
    )


def _clock(
    call: LiveOpenOptionPosition,
    *,
    opening_rows: Sequence[Mapping[str, object]],
    daily_bars: Sequence[Mapping[str, object]],
    option_market: Sequence[Mapping[str, object]],
    as_of: date,
) -> OpenCallClock:
    sold_on = min((_row_date(row) for row in opening_rows), default=as_of)
    underlying_at_sale = _close_on_or_before(
        call.underlying_symbol,
        sold_on,
        daily_bars,
    ) or call.underlying_price or ZERO
    original_dte = max(0, (call.expires_on - sold_on).days)
    elapsed_days = max(0, (as_of - sold_on).days)
    elapsed_percent = (
        min(HUNDRED, Decimal(elapsed_days) / Decimal(original_dte) * HUNDRED)
        if original_dte
        else HUNDRED
    )
    mark = call.estimated_mark_per_share or ZERO
    entry = call.entry_credit_per_share or ZERO
    contracts = Decimal(call.contracts)
    entry_credit = entry * CONTRACT_MULTIPLIER * contracts
    current_value = mark * CONTRACT_MULTIPLIER * contracts
    open_profit_loss = (
        call.open_profit_loss
        if call.open_profit_loss is not None
        else entry_credit - current_value
    )
    intrinsic_per_share = max(
        ZERO,
        (call.underlying_price or ZERO) - call.strike,
    )
    intrinsic_value = intrinsic_per_share * CONTRACT_MULTIPLIER * contracts
    time_value = max(ZERO, current_value - intrinsic_value)
    short_theta = max(
        ZERO,
        -(call.theta_per_share or ZERO) * CONTRACT_MULTIPLIER * contracts,
    )
    spread = max(ZERO, (call.ask_per_share or mark) - (call.bid_per_share or mark))
    spread_percent = spread / mark * HUNDRED if mark else ZERO
    remaining_percent = (
        Decimal(call.days_to_expiration) / Decimal(original_dte) * HUNDRED
        if original_dte
        else ZERO
    )
    return OpenCallClock(
        record_id=call.option_symbol,
        campaign_id=_campaign_id(opening_rows, call.option_symbol),
        policy_id="observed-live-position",
        sold_on=sold_on,
        expires_on=call.expires_on,
        strike=call.strike,
        contracts=call.contracts,
        underlying_at_sale=underlying_at_sale,
        close_ask_per_share=call.ask_per_share or mark,
        bid_per_share=call.bid_per_share or mark,
        spread_per_share=spread,
        spread_percent_of_mark=spread_percent,
        quote_observed_on=(
            call.quote_observed_at.date() if call.quote_observed_at is not None else None
        ),
        quote_status=(call.quote_quality or "unavailable").upper(),
        implied_volatility_percent=call.implied_volatility_percent,
        delta=call.delta,
        gamma=call.gamma,
        vega=call.vega,
        volume=call.volume,
        open_interest=call.open_interest,
        roll_quote_candidates=_roll_candidates(call, option_market),
        original_days_to_expiration=original_dte,
        elapsed_days=elapsed_days,
        elapsed_time_percent=elapsed_percent,
        days_to_expiration=call.days_to_expiration,
        strike_distance_per_share=call.strike_distance_per_share or ZERO,
        strike_distance_percent=call.strike_distance_percent or ZERO,
        mark_per_share=mark,
        entry_credit_per_share=entry,
        entry_credit=entry_credit,
        current_option_value=current_value,
        open_profit_loss=open_profit_loss,
        credit_capture_percent=(
            open_profit_loss / entry_credit * HUNDRED if entry_credit else ZERO
        ),
        option_value_vs_credit_percent=(
            current_value / entry_credit * HUNDRED if entry_credit else ZERO
        ),
        intrinsic_value=intrinsic_value,
        remaining_extrinsic_value=time_value,
        theta_per_share=call.theta_per_share or ZERO,
        short_theta_per_day=short_theta,
        theta_decay_percent_of_extrinsic=(
            short_theta / time_value * HUNDRED if time_value else ZERO
        ),
        theta_days_of_time_value=(time_value / short_theta if short_theta else ZERO),
        time_remaining_percent=max(ZERO, min(HUNDRED, remaining_percent)),
        decay_stage=_decay_stage(call.days_to_expiration, elapsed_percent),
    )


def _remaining_opening_rows(
    option_symbol: str,
    executions: Sequence[Mapping[str, object]],
) -> tuple[Mapping[str, object], ...]:
    rows = sorted(
        (
            row
            for row in executions
            if _canonical(str(row.get("symbol"))) == _canonical(option_symbol)
            and str(row.get("asset_type")) == "option"
        ),
        key=_row_date,
    )
    lots: list[list[object]] = []
    for row in rows:
        quantity = _decimal(row.get("quantity"))
        if str(row.get("side")) == "sell" and str(row.get("position_effect")) == "opening":
            lots.append([row, quantity])
        elif str(row.get("side")) == "buy" and str(row.get("position_effect")) == "closing":
            remaining = quantity
            while remaining > ZERO and lots:
                available = lots[0][1]
                assert isinstance(available, Decimal)
                consumed = min(available, remaining)
                available -= consumed
                remaining -= consumed
                lots[0][1] = available
                if available == ZERO:
                    lots.pop(0)
    return tuple(lot[0] for lot in lots)  # type: ignore[misc]


def _campaign_id(rows: Sequence[Mapping[str, object]], fallback: str) -> str:
    for row in reversed(rows):
        value = str(row.get("order_external_key") or row.get("external_key") or "")
        if value:
            return value
    return fallback


def _roll_candidates(
    call: LiveOpenOptionPosition,
    option_market: Sequence[Mapping[str, object]],
) -> tuple[RollQuoteCandidate, ...]:
    candidates: list[RollQuoteCandidate] = []
    for row in option_market:
        if _canonical(str(row.get("underlying_symbol") or "")) != _canonical(
            call.underlying_symbol
        ):
            continue
        if str(row.get("option_side") or "").lower() != "call":
            continue
        expiration = _date(row.get("expiration_date"))
        strike = _decimal(row.get("strike"))
        sell_bid = _decimal(row.get("bid"))
        if expiration <= call.expires_on or strike <= call.strike or sell_bid <= ZERO:
            continue
        quality = str(row.get("quote_quality") or "observed").replace("_", " ").upper()
        candidates.append(
            RollQuoteCandidate(
                expires_on=expiration,
                strike=strike,
                sell_bid_per_share=sell_bid,
                quote_source=f"SCHWAB CHAIN · {quality} BID",
            )
        )
    candidates.sort(key=lambda item: (item.expires_on, item.strike))
    return tuple(candidates)


def _close_on_or_before(
    symbol: str,
    value: date,
    daily_bars: Sequence[Mapping[str, object]],
) -> Decimal | None:
    rows = [
        row
        for row in daily_bars
        if str(row.get("symbol")) == symbol and _date(row.get("trade_date")) <= value
    ]
    if not rows:
        return None
    latest = max(rows, key=lambda row: _date(row.get("trade_date")))
    return _decimal(latest.get("close"))


def _decay_stage(days_to_expiration: int, elapsed_percent: Decimal) -> str:
    if days_to_expiration <= 7:
        return "EXPIRING SOON"
    if elapsed_percent < Decimal("33"):
        return "EARLY CYCLE"
    if elapsed_percent < Decimal("70"):
        return "MID CYCLE"
    return "LATE CYCLE"


def _row_date(row: Mapping[str, object]) -> date:
    return _date(row.get("occurred_at"))


def _date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _decimal(value: object) -> Decimal:
    return ZERO if value is None else Decimal(str(value))


def _canonical(value: str) -> str:
    return "".join(value.upper().split())
