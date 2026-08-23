from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal

from schwab_dashboard.application.campaigns import (
    campaign_record_key,
    reconcile_option_campaigns,
)
from schwab_dashboard.application.campaigns.models import CampaignLedger
from schwab_dashboard.application.dashboard.covered_calls import (
    OpenCallClock,
    RollQuoteCandidate,
)
from schwab_dashboard.application.dashboard.models import LiveOpenOptionPosition
from schwab_dashboard.application.rolls.collect import collect_roll_quotes
from schwab_dashboard.application.rolls.models import RollQuote
from schwab_dashboard.domain.instruments import OptionSide

ZERO = Decimal("0")
HUNDRED = Decimal("100")


def build_open_call_clocks(
    symbol: str,
    calls: Sequence[LiveOpenOptionPosition],
    *,
    executions: Sequence[Mapping[str, object]],
    daily_bars: Sequence[Mapping[str, object]],
    option_market: Sequence[Mapping[str, object]] = (),
    as_of: date,
) -> tuple[OpenCallClock, ...]:
    campaign_ledger = reconcile_option_campaigns(executions, ())
    return tuple(
        _clock(
            call,
            opening_rows=remaining_opening_rows(call.option_symbol, executions),
            campaign_ledger=campaign_ledger,
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
    campaign_ledger: CampaignLedger,
    daily_bars: Sequence[Mapping[str, object]],
    option_market: Sequence[Mapping[str, object]],
    as_of: date,
) -> OpenCallClock:
    campaign_id, campaign_label = _campaign_identity(
        opening_rows,
        fallback=call.option_symbol,
        campaign_ledger=campaign_ledger,
    )
    sold_on = min((_row_date(row) for row in opening_rows), default=as_of)
    underlying_at_sale = (
        _close_on_or_before(
            call.underlying_symbol,
            sold_on,
            daily_bars,
        )
        or call.underlying_price
        or ZERO
    )
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
    multiplier = call.contract_multiplier
    entry_credit = entry * multiplier * contracts
    current_value = mark * multiplier * contracts
    open_profit_loss = (
        call.open_profit_loss if call.open_profit_loss is not None else entry_credit - current_value
    )
    intrinsic_per_share = max(
        ZERO,
        (call.underlying_price or ZERO) - call.strike,
    )
    intrinsic_value = intrinsic_per_share * multiplier * contracts
    time_value = max(ZERO, current_value - intrinsic_value)
    short_theta = max(
        ZERO,
        -(call.theta_per_share or ZERO) * multiplier * contracts,
    )
    if not call.can_close_or_roll:
        short_theta = ZERO
    spread = max(ZERO, (call.ask_per_share or mark) - (call.bid_per_share or mark))
    spread_percent = spread / mark * HUNDRED if mark else ZERO
    remaining_percent = (
        Decimal(call.days_to_expiration) / Decimal(original_dte) * HUNDRED if original_dte else ZERO
    )
    return OpenCallClock(
        record_id=call.option_symbol,
        campaign_id=campaign_id,
        campaign_label=campaign_label,
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
        roll_quote_candidates=(
            _as_clock_quotes(
                collect_roll_quotes(
                    underlying_symbol=call.underlying_symbol,
                    option_side=OptionSide.CALL,
                    source_expiration=call.expires_on,
                    source_strike=call.strike,
                    source_option_symbol=call.option_symbol,
                    option_market=option_market,
                )
            )
            if call.can_close_or_roll
            else ()
        ),
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
        decay_stage=(
            _decay_stage(call.days_to_expiration, elapsed_percent)
            if call.can_close_or_roll
            else call.session_label
        ),
        session_state=call.session_state,
        contract_multiplier=call.contract_multiplier,
        price_time_read=call.price_time_read,
        quote_observed_at=call.quote_observed_at,
        expiration_assessment=call.expiration_assessment,
    )


def remaining_opening_rows(
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


def remaining_open_lot_date(
    option_symbol: str,
    executions: Sequence[Mapping[str, object]],
) -> date | None:
    """Return the oldest still-open short lot date for an option contract.

    Opening sells are matched FIFO against closing buys.  Keeping this logic in
    one place prevents call and put clocks from disagreeing after partial closes.
    """

    rows = remaining_opening_rows(option_symbol, executions)
    return min((_row_date(row) for row in rows), default=None)


def _campaign_identity(
    rows: Sequence[Mapping[str, object]],
    *,
    fallback: str,
    campaign_ledger: CampaignLedger,
) -> tuple[str, str]:
    """Return the reconciled identity of the lot that is still open.

    A live option series can have historical legs in several campaigns. Using
    the latest order id (the former behavior) does not identify which campaign
    still owns the position and forces the chart UI to guess by strike/date.
    Resolve the surviving opening rows against the same ledger that draws the
    chart instead. When one aggregated position genuinely spans several
    campaigns, do not claim that any single path owns the whole line.
    """

    identities: dict[str, str] = {}
    for row in rows:
        annotation = campaign_ledger.annotation_for(campaign_record_key(row))
        if annotation is not None:
            identities[annotation.campaign_id] = annotation.campaign_label
    if len(identities) == 1:
        return next(iter(identities.items()))
    if len(identities) > 1:
        return fallback, f"{len(identities)} CAMPAIGNS"
    return fallback, ""


def _as_clock_quotes(quotes: Sequence[RollQuote]) -> tuple[RollQuoteCandidate, ...]:
    return tuple(
        RollQuoteCandidate(
            expires_on=quote.expires_on,
            strike=quote.strike,
            sell_bid_per_share=quote.sell_bid_per_share,
            quote_source=quote.quote_source,
            option_symbol=quote.option_symbol,
            spread_percent=quote.spread_percent,
            open_interest=quote.open_interest,
            volume=quote.volume,
            theta_per_share=quote.theta_per_share,
            quote_observed_at=quote.quote_observed_at,
        )
        for quote in quotes
    )


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


def _optional_int(value: object) -> int | None:
    return None if value is None else int(str(value))


def _canonical(value: str) -> str:
    return "".join(value.upper().split())
