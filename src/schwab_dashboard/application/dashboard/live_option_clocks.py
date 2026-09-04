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
from schwab_dashboard.application.dashboard.short_premium import (
    is_closing_buy,
    is_opening_sale,
    is_option_execution,
)
from schwab_dashboard.application.market_time import ledger_market_date, market_date
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
            opening_rows=remaining_opening_rows(
                call.option_symbol,
                executions,
                account_id=call.account_id,
                account_mask=call.account_mask,
            ),
            campaign_ledger=campaign_ledger,
            daily_bars=daily_bars,
            option_market=option_market,
            as_of=as_of,
        )
        for call in calls
        if _canonical(call.underlying_symbol) == _canonical(symbol)
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
    sold_on = min((_row_date(row) for row in opening_rows), default=call.opened_on)
    underlying_at_sale = (
        _close_on_or_before(call.underlying_symbol, sold_on, daily_bars)
        if sold_on is not None
        else None
    )
    original_dte = (
        max(0, (call.expires_on - sold_on).days)
        if sold_on is not None
        else call.original_days_to_expiration
    )
    elapsed_days = max(0, (as_of - sold_on).days) if sold_on is not None else None
    elapsed_percent = (
        min(HUNDRED, Decimal(elapsed_days) / Decimal(original_dte) * HUNDRED)
        if elapsed_days is not None and original_dte
        else HUNDRED
        if elapsed_days is not None and original_dte == 0
        else None
    )
    mark = abs(call.estimated_mark_per_share) if call.estimated_mark_per_share is not None else None
    entry = abs(call.entry_credit_per_share) if call.entry_credit_per_share is not None else None
    contracts = Decimal(call.contracts)
    multiplier = abs(call.contract_multiplier)
    entry_credit = entry * multiplier * contracts if entry is not None else None
    current_value = call.current_option_value
    open_profit_loss = (
        call.open_profit_loss
        if call.open_profit_loss is not None
        else entry_credit - current_value
        if entry_credit is not None and current_value is not None
        else None
    )
    intrinsic_value = (
        max(ZERO, call.underlying_price - call.strike)
        * call.deliverable_shares_per_contract
        * contracts
        if call.underlying_price is not None and call.deliverable_shares_per_contract is not None
        else None
    )
    time_value = (
        max(ZERO, current_value - intrinsic_value)
        if current_value is not None and intrinsic_value is not None
        else None
    )
    short_theta = (
        max(ZERO, -call.theta_per_share * multiplier * contracts)
        if call.theta_per_share is not None and call.can_close_or_roll
        else ZERO
        if not call.can_close_or_roll
        else None
    )
    spread = (
        max(ZERO, call.ask_per_share - call.bid_per_share)
        if call.ask_per_share is not None and call.bid_per_share is not None
        else None
    )
    spread_percent = (
        spread / mark * HUNDRED
        if spread is not None and mark is not None and mark != ZERO
        else None
    )
    remaining_percent = (
        Decimal(call.days_to_expiration) / Decimal(original_dte) * HUNDRED
        if original_dte
        else ZERO
        if original_dte == 0
        else None
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
        close_ask_per_share=call.ask_per_share,
        bid_per_share=call.bid_per_share,
        spread_per_share=spread,
        spread_percent_of_mark=spread_percent,
        quote_observed_on=(
            market_date(call.quote_observed_at) if call.quote_observed_at is not None else None
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
        strike_distance_per_share=call.strike_distance_per_share,
        strike_distance_percent=call.strike_distance_percent,
        mark_per_share=mark,
        entry_credit_per_share=entry,
        entry_credit=entry_credit,
        current_option_value=current_value,
        open_profit_loss=open_profit_loss,
        credit_capture_percent=(
            open_profit_loss / entry_credit * HUNDRED
            if open_profit_loss is not None and entry_credit
            else None
        ),
        option_value_vs_credit_percent=(
            current_value / entry_credit * HUNDRED
            if current_value is not None and entry_credit
            else None
        ),
        intrinsic_value=intrinsic_value,
        remaining_extrinsic_value=time_value,
        theta_per_share=call.theta_per_share,
        short_theta_per_day=short_theta,
        theta_decay_percent_of_extrinsic=(
            short_theta / time_value * HUNDRED if short_theta is not None and time_value else None
        ),
        theta_days_of_time_value=(
            time_value / short_theta if time_value is not None and short_theta else None
        ),
        time_remaining_percent=(
            max(ZERO, min(HUNDRED, remaining_percent)) if remaining_percent is not None else None
        ),
        decay_stage=(
            _decay_stage(call.days_to_expiration, elapsed_percent)
            if call.can_close_or_roll
            else call.session_label
        ),
        session_state=call.session_state,
        contract_multiplier=call.contract_multiplier,
        deliverable_shares_per_contract=call.deliverable_shares_per_contract,
        price_time_read=call.price_time_read,
        quote_observed_at=call.quote_observed_at,
        expiration_assessment=call.expiration_assessment,
        account_mask=call.account_mask,
        account_id=call.account_id,
    )


def remaining_opening_rows(
    option_symbol: str,
    executions: Sequence[Mapping[str, object]],
    *,
    account_id: str | None = None,
    account_mask: str | None = None,
) -> tuple[Mapping[str, object], ...]:
    rows = sorted(
        (
            row
            for row in executions
            if _canonical(str(row.get("symbol"))) == _canonical(option_symbol)
            and is_option_execution(row)
            and _matches_account(row, account_id=account_id, account_mask=account_mask)
        ),
        key=_row_date,
    )
    lots: list[list[object]] = []
    for row in rows:
        quantity = _decimal(row.get("quantity"))
        if is_opening_sale(row):
            lots.append([row, quantity])
        elif is_closing_buy(row):
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
    *,
    account_id: str | None = None,
    account_mask: str | None = None,
) -> date | None:
    """Return the oldest still-open short lot date for an option contract.

    Opening sells are matched FIFO against closing buys.  Keeping this logic in
    one place prevents call and put clocks from disagreeing after partial closes.
    """

    rows = remaining_opening_rows(
        option_symbol,
        executions,
        account_id=account_id,
        account_mask=account_mask,
    )
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
    rows = []
    for row in daily_bars:
        close = _optional_decimal(row.get("close"))
        if (
            _canonical(str(row.get("symbol") or "")) == _canonical(symbol)
            and _date(row.get("trade_date")) <= value
            and close is not None
            and close > ZERO
        ):
            rows.append(row)
    if not rows:
        return None
    latest = max(rows, key=lambda row: _date(row.get("trade_date")))
    return _optional_decimal(latest.get("close"))


def _decay_stage(days_to_expiration: int, elapsed_percent: Decimal | None) -> str:
    if days_to_expiration <= 7:
        return "EXPIRING SOON"
    if elapsed_percent is None:
        return "TERM UNKNOWN"
    if elapsed_percent < Decimal("33"):
        return "EARLY CYCLE"
    if elapsed_percent < Decimal("70"):
        return "MID CYCLE"
    return "LATE CYCLE"


def _row_date(row: Mapping[str, object]) -> date:
    value = row.get("occurred_at")
    if isinstance(value, (date, datetime)):
        return ledger_market_date(value)
    return _date(value)


def _date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _decimal(value: object) -> Decimal:
    return ZERO if value is None else Decimal(str(value))


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _matches_account(
    row: Mapping[str, object],
    *,
    account_id: str | None,
    account_mask: str | None,
) -> bool:
    row_account_id = str(row.get("account_id") or "").strip()
    if account_id and row_account_id:
        return row_account_id == account_id
    row_mask = str(row.get("account_mask") or "").strip()
    return not row_mask or not account_mask or row_mask == account_mask


def _optional_int(value: object) -> int | None:
    return None if value is None else int(str(value))


def _canonical(value: str) -> str:
    return "".join(value.upper().split())
