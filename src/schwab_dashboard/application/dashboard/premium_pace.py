from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from schwab_dashboard.application.dashboard.covered_calls import UnderlyingCallStats
from schwab_dashboard.application.dashboard.models import (
    LiveOpenOptionPosition,
    LivePositionBook,
    OpenPremiumPace,
)
from schwab_dashboard.application.dashboard.short_premium import (
    is_closing_buy,
    is_opening_sale,
    is_option_execution,
)
from schwab_dashboard.application.market_time import ledger_market_date
from schwab_dashboard.application.values import sum_if_complete

ZERO = Decimal("0")
ONE = Decimal("1")


@dataclass(frozen=True, slots=True)
class _OpenLot:
    opened_on: date
    contracts: Decimal
    credit_per_share: Decimal


def build_open_premium_pace(
    book: LivePositionBook,
    executions: Sequence[Mapping[str, object]],
) -> OpenPremiumPace:
    """Normalize live short-option credits over their original calendar terms.

    Current broker positions are authoritative for contracts and entry credit.
    Executions are used only to recover the opening date of each remaining lot.
    If the execution inventory cannot reconcile to a live position, the strong
    daily figure is withheld instead of extrapolating an unverified term.
    """

    options = tuple(option for option in (*book.calls, *book.puts) if option.can_close_or_roll)
    total_contracts = sum(option.contracts for option in options)
    opening_credits: list[Decimal | None] = []
    daily_pace = ZERO
    timed_contracts = 0

    for option in options:
        entry = option.entry_credit_per_share
        if entry is None:
            opening_credits.append(None)
            continue
        line_credit = abs(entry) * option.contract_multiplier * Decimal(option.contracts)
        opening_credits.append(line_credit)
        lots = _remaining_open_lots(option, executions)
        if sum((lot.contracts for lot in lots), ZERO) != Decimal(option.contracts):
            continue

        weighted_inverse_term = _weighted_inverse_term(
            lots,
            expires_on=option.expires_on,
            fallback_credit=abs(entry),
        )
        if weighted_inverse_term is None:
            continue
        daily_pace += line_credit * weighted_inverse_term
        timed_contracts += option.contracts

    complete = total_contracts > 0 and timed_contracts == total_contracts
    opening_credit = sum_if_complete(opening_credits)
    verified_pace = daily_pace if complete else None
    weighted_term = (
        opening_credit / daily_pace
        if complete and opening_credit is not None and daily_pace > ZERO
        else None
    )
    return OpenPremiumPace(
        daily_pace=verified_pace,
        opening_credit=opening_credit,
        weighted_term_days=weighted_term,
        timed_contracts=timed_contracts,
        total_contracts=total_contracts,
    )


def build_demo_premium_pace(
    underlyings: Sequence[UnderlyingCallStats],
) -> OpenPremiumPace:
    """Build the same pace from fully modeled demo call clocks."""

    clocks = tuple(
        clock for item in underlyings for clock in item.open_call_clocks if clock.can_close_or_roll
    )
    opening_credit = sum_if_complete(clock.entry_credit for clock in clocks)
    daily_pace = sum_if_complete(
        clock.entry_credit / Decimal(max(1, clock.original_days_to_expiration))
        if clock.entry_credit is not None and clock.original_days_to_expiration is not None
        else None
        for clock in clocks
    )
    contracts = sum(clock.contracts for clock in clocks)
    return OpenPremiumPace(
        daily_pace=daily_pace if contracts else ZERO,
        opening_credit=opening_credit,
        weighted_term_days=(
            opening_credit / daily_pace if opening_credit is not None and daily_pace else None
        ),
        timed_contracts=(contracts if daily_pace is not None else 0),
        total_contracts=contracts,
    )


def _remaining_open_lots(
    option: LiveOpenOptionPosition,
    executions: Sequence[Mapping[str, object]],
) -> tuple[_OpenLot, ...]:
    rows = sorted(
        (row for row in executions if _matches_option(row, option) and is_option_execution(row)),
        key=_row_date,
    )
    lots: list[_OpenLot] = []
    for row in rows:
        quantity = abs(_decimal(row.get("quantity")))
        if quantity <= ZERO:
            continue
        if is_opening_sale(row):
            lots.append(
                _OpenLot(
                    opened_on=_row_date(row),
                    contracts=quantity,
                    credit_per_share=abs(_decimal(row.get("price"))),
                )
            )
        elif is_closing_buy(row):
            _consume_fifo(lots, quantity)
    return tuple(lot for lot in lots if lot.contracts > ZERO)


def _weighted_inverse_term(
    lots: Sequence[_OpenLot],
    *,
    expires_on: date,
    fallback_credit: Decimal,
) -> Decimal | None:
    weighted_terms: list[tuple[Decimal, Decimal]] = []
    for lot in lots:
        term_days = (expires_on - lot.opened_on).days
        if term_days < 0:
            return None
        term_days = max(1, term_days)
        credit_weight = lot.credit_per_share or fallback_credit
        weight = lot.contracts * credit_weight
        weighted_terms.append((weight, Decimal(term_days)))
    if not weighted_terms:
        return None
    total_weight = sum((weight for weight, _ in weighted_terms), ZERO)
    if total_weight <= ZERO:
        weighted_terms = [
            (lot.contracts, Decimal(max(1, (expires_on - lot.opened_on).days))) for lot in lots
        ]
        total_weight = sum((weight for weight, _ in weighted_terms), ZERO)
    if total_weight <= ZERO:
        return None
    return sum((weight / term for weight, term in weighted_terms), ZERO) / total_weight


def _consume_fifo(lots: list[_OpenLot], quantity: Decimal) -> None:
    remaining = quantity
    while remaining > ZERO and lots:
        lot = lots[0]
        consumed = min(lot.contracts, remaining)
        remaining -= consumed
        available = lot.contracts - consumed
        if available == ZERO:
            lots.pop(0)
        else:
            lots[0] = _OpenLot(
                opened_on=lot.opened_on,
                contracts=available,
                credit_per_share=lot.credit_per_share,
            )


def _matches_option(row: Mapping[str, object], option: LiveOpenOptionPosition) -> bool:
    if _canonical(str(row.get("symbol") or "")) != _canonical(option.option_symbol):
        return False
    account_id = str(row.get("account_id") or "").strip()
    if option.account_id and account_id:
        return account_id == option.account_id
    account = str(row.get("account_mask") or "").strip()
    return not account or account == option.account_mask


def _row_date(row: Mapping[str, object]) -> date:
    value = row.get("occurred_at")
    if isinstance(value, (date, datetime)):
        return ledger_market_date(value)
    raise ValueError("Option execution is missing its source date")


def _decimal(value: object) -> Decimal:
    return ZERO if value is None else Decimal(str(value))


def _canonical(value: str) -> str:
    return "".join(value.upper().split())
