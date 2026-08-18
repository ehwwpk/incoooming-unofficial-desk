from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from schwab_dashboard.domain.instruments import OptionSide
from schwab_dashboard.domain.market import QuoteQuality, UnderlyingDailyBar
from schwab_dashboard.domain.opportunity_map import RadarExpirationMap
from schwab_dashboard.domain.validation import require_aware, require_text


class RadarMode(StrEnum):
    COVERED_CALL = "covered_call"
    CASH_SECURED_PUT = "cash_secured_put"

    @property
    def option_side(self) -> OptionSide:
        return OptionSide.CALL if self is RadarMode.COVERED_CALL else OptionSide.PUT


class RadarState(StrEnum):
    IDLE = "idle"
    READY = "ready"
    WAIT = "wait"
    PARTIAL = "partial"
    STALE = "stale"
    AUTHORIZATION_REQUIRED = "authorization_required"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


class RadarCandidateLabel(StrEnum):
    MORE_ROOM = "more_room"
    BALANCED = "balanced"
    MORE_CREDIT = "more_credit"
    NEAR_FLAT = "near_flat"
    NET_CREDIT = "net_credit"
    DEBIT_FOR_ROOM = "debit_for_room"


class RadarGateStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class RadarGate:
    code: str
    label: str
    status: RadarGateStatus
    detail: str

    def __post_init__(self) -> None:
        require_text(self.code, "code")
        require_text(self.label, "label")
        require_text(self.detail, "detail")


@dataclass(frozen=True, slots=True)
class RadarPolicy:
    symbol: str
    mode: RadarMode
    version: int = 1
    minimum_dte: int = 5
    maximum_dte: int = 60
    minimum_annualized_rate_percent: Decimal = Decimal("5")
    minimum_strike: Decimal | None = None
    minimum_strike_distance_percent: Decimal = Decimal("0")
    maximum_effective_entry: Decimal | None = None
    maximum_spread_percent: Decimal | None = None
    minimum_open_interest: int = 0
    minimum_volume: int = 0
    maximum_quote_age_seconds: int = 86400
    allowed_contracts: int = 1
    reserved_cash: Decimal = Decimal("0")
    maximum_five_day_move_percent: Decimal | None = None

    def __post_init__(self) -> None:
        require_text(self.symbol, "symbol")
        if self.version < 1:
            raise ValueError("version must be positive")
        if self.minimum_dte < 0 or self.maximum_dte < self.minimum_dte:
            raise ValueError("DTE range must be non-negative and ordered")
        if self.minimum_annualized_rate_percent < 0:
            raise ValueError("minimum annualized premium rate must be non-negative")
        if self.minimum_strike is not None and self.minimum_strike < 0:
            raise ValueError("minimum_strike must be non-negative")
        if self.minimum_strike_distance_percent < 0:
            raise ValueError("minimum_strike_distance_percent must be non-negative")
        if self.maximum_effective_entry is not None and self.maximum_effective_entry < 0:
            raise ValueError("maximum_effective_entry must be non-negative")
        if self.maximum_spread_percent is not None and self.maximum_spread_percent < 0:
            raise ValueError("maximum_spread_percent must be non-negative")
        if self.minimum_open_interest < 0 or self.minimum_volume < 0:
            raise ValueError("liquidity limits must be non-negative")
        if self.maximum_quote_age_seconds < 1:
            raise ValueError("maximum_quote_age_seconds must be positive")
        if self.allowed_contracts < 0:
            raise ValueError("allowed_contracts must be non-negative")
        if self.reserved_cash < 0:
            raise ValueError("reserved_cash must be non-negative")
        if (
            self.maximum_five_day_move_percent is not None
            and self.maximum_five_day_move_percent < 0
        ):
            raise ValueError("maximum_five_day_move_percent must be non-negative")


@dataclass(frozen=True, slots=True)
class RadarAccountContext:
    shares: int
    covered_call_contracts: int
    available_call_lots: int
    reserved_cash: Decimal
    account_mask: str | None = None

    def __post_init__(self) -> None:
        if self.shares < 0 or self.covered_call_contracts < 0 or self.available_call_lots < 0:
            raise ValueError("account quantities must be non-negative")
        if self.reserved_cash < 0:
            raise ValueError("reserved_cash must be non-negative")


@dataclass(frozen=True, slots=True)
class RadarMarketContract:
    option_symbol: str
    underlying_symbol: str
    option_side: OptionSide
    expiration_date: date
    strike: Decimal
    multiplier: Decimal
    observed_at: datetime
    quote_quality: QuoteQuality
    bid: Decimal | None
    ask: Decimal | None
    last: Decimal | None
    mark: Decimal | None
    underlying_price: Decimal | None
    implied_volatility: Decimal | None
    delta: Decimal | None
    gamma: Decimal | None
    theta: Decimal | None
    vega: Decimal | None
    volume: int | None
    open_interest: int | None

    def __post_init__(self) -> None:
        require_text(self.option_symbol, "option_symbol")
        require_text(self.underlying_symbol, "underlying_symbol")
        require_aware(self.observed_at, "observed_at")
        if self.strike < 0 or self.multiplier <= 0:
            raise ValueError("strike and multiplier must be valid")


@dataclass(frozen=True, slots=True)
class RadarMarketBundle:
    source: str
    symbol: str
    observed_at: datetime
    underlying_price: Decimal | None
    contracts: tuple[RadarMarketContract, ...]
    daily_bars: tuple[UnderlyingDailyBar, ...]
    capabilities: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        require_text(self.source, "source")
        require_text(self.symbol, "symbol")
        require_aware(self.observed_at, "observed_at")


@dataclass(frozen=True, slots=True)
class RadarCandidate:
    option_symbol: str
    label: RadarCandidateLabel | None
    strike: Decimal
    expiration_date: date
    days_to_expiration: int
    bid: Decimal
    ask: Decimal
    midpoint: Decimal
    spread_dollars: Decimal
    spread_percent: Decimal
    room_dollars: Decimal
    room_percent: Decimal
    expected_move: Decimal | None
    strike_distance_in_moves: Decimal | None
    delta: Decimal | None
    implied_volatility: Decimal | None
    open_interest: int | None
    volume: int | None
    quote_observed_at: datetime
    premium_per_contract: Decimal
    bid_credit_per_calendar_day: Decimal
    premium_dollars: Decimal
    simple_annualized_rate_percent: Decimal
    effective_entry: Decimal | None
    cash_required: Decimal | None
    eligible_contracts: int
    clears_all_rules: bool
    gates: tuple[RadarGate, ...]
    reasons: tuple[str, ...]
    theta: Decimal | None = None


@dataclass(frozen=True, slots=True)
class RadarRollComparison:
    """Two-leg economics for one replacement call in a roll review."""

    option_symbol: str
    expiration_date: date
    strike: Decimal
    bid_per_share: Decimal
    net_roll_per_share: Decimal
    net_roll_cash: Decimal
    strike_change_per_share: Decimal
    added_days: int


@dataclass(frozen=True, slots=True)
class RadarRollSelectionContext:
    """The open short option that replacement candidates must improve."""

    option_side: OptionSide
    source_expiration_date: date
    source_strike: Decimal
    source_close_ask_per_share: Decimal
    source_current_price: Decimal = Decimal("0")


@dataclass(frozen=True, slots=True)
class RadarRollReview:
    """Server-verified context for replacing one open short option."""

    source_option_symbol: str
    source_option_side: OptionSide
    source_expiration_date: date
    source_strike: Decimal
    source_contracts: int
    source_close_ask_per_share: Decimal
    source_quote_status: str
    target_expiration_date: date | None
    target_strike: Decimal | None
    target_bid_per_share: Decimal | None
    net_roll_per_share: Decimal | None
    net_roll_cash: Decimal | None
    strike_lift_per_share: Decimal | None
    added_days: int | None
    status: str
    comparisons: tuple[RadarRollComparison, ...] = ()


@dataclass(frozen=True, slots=True)
class RadarProjection:
    lookup_id: str | None
    state: RadarState
    symbol: str | None
    mode: RadarMode
    source: str
    observed_at: datetime | None
    underlying_price: Decimal | None
    account: RadarAccountContext
    policy: RadarPolicy
    verdict: str
    headline: str
    reasons: tuple[str, ...]
    candidates: tuple[RadarCandidate, ...]
    rejected_count: int
    warnings: tuple[str, ...]
    expiration_map: RadarExpirationMap | None
    five_day_move_percent: Decimal | None = None
    twenty_day_move_percent: Decimal | None = None
    range_position_percent: Decimal | None = None
    roll_review: RadarRollReview | None = None
