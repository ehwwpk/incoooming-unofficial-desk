from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from schwab_dashboard.domain.instruments import OptionSide


@dataclass(frozen=True, slots=True)
class RollSource:
    symbol: str
    option_symbol: str
    option_side: OptionSide
    expires_on: date
    strike: Decimal
    contracts: int
    close_ask_per_share: Decimal
    current_price: Decimal
    quote_status: str
    contract_multiplier: Decimal = Decimal("100")


@dataclass(frozen=True, slots=True)
class RollQuote:
    option_symbol: str
    expires_on: date
    strike: Decimal
    sell_bid_per_share: Decimal
    quote_source: str
    spread_percent: Decimal | None = None
    open_interest: int | None = None
    volume: int | None = None


@dataclass(frozen=True, slots=True)
class RollCandidate:
    option_symbol: str
    option_side: OptionSide
    expires_on: date
    strike: Decimal
    sell_bid_per_share: Decimal
    net_roll_per_share: Decimal
    net_roll_cash: Decimal
    strike_change_per_share: Decimal
    added_days: int
    assignment_room_gain: Decimal
    target_buffer_percent: Decimal
    cost_label: str
    family_label: str
    quote_source: str
    spread_percent: Decimal | None
    open_interest: int | None
    volume: int | None


@dataclass(frozen=True, slots=True)
class RollSearchResult:
    source: RollSource
    candidates: tuple[RollCandidate, ...]
    examined_quotes: int
    eligible_quotes: int
    no_clean_reason: str | None = None
