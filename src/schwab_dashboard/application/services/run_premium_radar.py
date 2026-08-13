from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import httpx

from schwab_dashboard.application.dashboard.covered_calls import OpenCallClock
from schwab_dashboard.application.dashboard.models import DashboardSnapshot
from schwab_dashboard.application.errors import AuthenticationRequiredError
from schwab_dashboard.application.opportunities import evaluate_radar
from schwab_dashboard.application.opportunities.symbol import normalize_symbol
from schwab_dashboard.application.ports.dashboard import DashboardReader
from schwab_dashboard.application.ports.opportunity_market import OpportunityMarketGateway
from schwab_dashboard.application.ports.opportunity_store import OpportunityStore
from schwab_dashboard.domain.opportunity import (
    RadarAccountContext,
    RadarMarketBundle,
    RadarMarketContract,
    RadarMode,
    RadarPolicy,
    RadarProjection,
    RadarRollComparison,
    RadarRollReview,
    RadarRollSelectionContext,
)


class AuthorizationRequiredOpportunityMarketGateway:
    def fetch(
        self,
        *,
        symbol: str,
        mode: RadarMode,
        from_date: date,
        to_date: date,
    ) -> RadarMarketBundle:
        del symbol, mode, from_date, to_date
        raise AuthenticationRequiredError(
            "The selected Schwab connection needs authorization before Radar can load a chain."
        )


@dataclass(frozen=True, slots=True)
class RadarDefaults:
    minimum_dte: int
    maximum_dte: int
    minimum_annualized_rate_percent: Decimal
    maximum_spread_percent: Decimal
    minimum_open_interest: int
    minimum_volume: int
    maximum_quote_age_seconds: int
    maximum_five_day_move_percent: Decimal | None


@dataclass(frozen=True, slots=True)
class RadarRollRequest:
    source_option_symbol: str
    target_expiration: date
    target_strike: Decimal


class RadarRollRequestError(LookupError):
    """The requested source leg or replacement is not a valid live roll review."""


class RadarLookupError(RuntimeError):
    def __init__(self, message: str, *, lookup_id: str, state: str) -> None:
        super().__init__(message)
        self.lookup_id = lookup_id
        self.state = state


class RunPremiumRadar:
    def __init__(
        self,
        *,
        market: OpportunityMarketGateway,
        store: OpportunityStore,
        dashboard_factory: Callable[[], DashboardReader],
        defaults: RadarDefaults,
        source: str = "schwab",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._market = market
        self._store = store
        self._dashboard_factory = dashboard_factory
        self._defaults = defaults
        self._source = source
        self._clock = clock or (lambda: datetime.now(UTC))

    def execute(
        self,
        *,
        symbol: str,
        mode: RadarMode,
        snapshot: DashboardSnapshot | None = None,
        roll_request: RadarRollRequest | None = None,
    ) -> RadarProjection:
        canonical = normalize_symbol(symbol)
        requested_at = self._clock()
        lookup_id = self._store.create_lookup(
            symbol=canonical,
            mode=mode,
            source=self._source,
            requested_at=requested_at,
        )
        try:
            account_snapshot = snapshot or self._dashboard_factory().execute()
            policy = self.policy_for(symbol=canonical, mode=mode)
            roll_source = _resolve_roll_source(
                account_snapshot,
                symbol=canonical,
                mode=mode,
                request=roll_request,
            )
            account = _account_context(
                account_snapshot,
                symbol=canonical,
                policy=policy,
                released_call_contracts=(roll_source.contracts if roll_source else 0),
            )
            scan_from = _expiration_date(
                requested_at.date(), policy.minimum_dte, field="minimum_dte"
            )
            scan_to = _expiration_date(requested_at.date(), policy.maximum_dte, field="maximum_dte")
            if roll_source is not None and roll_request is not None:
                scan_from = min(
                    scan_from,
                    max(requested_at.date(), roll_source.expires_on),
                )
                scan_to = max(scan_to, roll_request.target_expiration)
            bundle = self._market.fetch(
                symbol=canonical,
                mode=mode,
                from_date=scan_from,
                to_date=scan_to,
            )
            roll_selection = (
                _roll_selection_context(bundle, roll_source) if roll_source is not None else None
            )
            projection = evaluate_radar(
                lookup_id=lookup_id,
                bundle=bundle,
                mode=mode,
                account=account,
                policy=policy,
                now=self._clock(),
                preferred_strike=(roll_request.target_strike if roll_request else None),
                preferred_expiration=(roll_request.target_expiration if roll_request else None),
                roll_selection=roll_selection,
            )
            if roll_request is not None and roll_source is not None:
                projection = replace(
                    projection,
                    roll_review=_build_roll_review(
                        projection,
                        bundle=bundle,
                        source=roll_source,
                        request=roll_request,
                    ),
                )
            self._store.complete_lookup(projection, completed_at=self._clock())
            return projection
        except AuthenticationRequiredError as exc:
            self._fail(lookup_id, state="authorization_required", error=exc)
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            if status_code in {401, 403}:
                state = "authorization_required"
            elif status_code in {400, 404, 422}:
                state = "unsupported"
            else:
                state = "failed"
            self._fail(lookup_id, state=state, error=exc)
        except LookupError as exc:
            self._fail(lookup_id, state="unsupported", error=exc)
        except (TypeError, ValueError) as exc:
            self._fail(lookup_id, state="failed", error=exc)
        raise AssertionError("Radar failure handling must raise")

    def policy_for(self, *, symbol: str, mode: RadarMode) -> RadarPolicy:
        canonical = normalize_symbol(symbol)
        saved = self._store.load_policy(symbol=canonical, mode=mode)
        if saved is not None:
            return saved
        return RadarPolicy(
            symbol=canonical,
            mode=mode,
            minimum_dte=self._defaults.minimum_dte,
            maximum_dte=self._defaults.maximum_dte,
            minimum_annualized_rate_percent=(self._defaults.minimum_annualized_rate_percent),
            minimum_strike_distance_percent=(
                Decimal("5") if mode is RadarMode.CASH_SECURED_PUT else Decimal("0")
            ),
            maximum_spread_percent=self._defaults.maximum_spread_percent,
            minimum_open_interest=self._defaults.minimum_open_interest,
            minimum_volume=self._defaults.minimum_volume,
            maximum_quote_age_seconds=self._defaults.maximum_quote_age_seconds,
            maximum_five_day_move_percent=self._defaults.maximum_five_day_move_percent,
        )

    def save_policy(self, policy: RadarPolicy) -> RadarPolicy:
        canonical = normalize_symbol(policy.symbol)
        current = self._store.load_policy(symbol=canonical, mode=policy.mode)
        requested_version = current.version if current is not None else 1
        return self._store.save_policy(replace(policy, symbol=canonical, version=requested_version))

    def held_symbols(self, snapshot: DashboardSnapshot | None = None) -> tuple[str, ...]:
        account_snapshot = snapshot or self._dashboard_factory().execute()
        if account_snapshot.live_position_book is not None:
            symbols = (item.symbol for item in account_snapshot.live_position_book.underlyings)
        else:
            symbols = (item.symbol for item in account_snapshot.underlyings)
        return tuple(sorted(symbols))

    def saved_symbols(self) -> tuple[str, ...]:
        return self._store.list_saved_symbols(source=self._source)

    def save_symbol(self, symbol: str) -> None:
        self._store.save_symbol(
            symbol=normalize_symbol(symbol),
            source=self._source,
            saved_at=self._clock(),
        )

    def remove_symbol(self, symbol: str) -> None:
        self._store.remove_symbol(symbol=normalize_symbol(symbol), source=self._source)

    def load_lookup(self, lookup_id: str) -> dict[str, object] | None:
        return self._store.load_lookup(lookup_id)

    def _fail(self, lookup_id: str, *, state: str, error: Exception) -> None:
        message = _safe_error_message(error, state=state)
        self._store.fail_lookup(
            lookup_id,
            state=state,
            error_message=message,
            completed_at=self._clock(),
        )
        raise RadarLookupError(message, lookup_id=lookup_id, state=state) from error


def _expiration_date(as_of: date, dte: int, *, field: str) -> date:
    try:
        return as_of + timedelta(days=dte)
    except OverflowError as exc:
        raise ValueError(f"{field} exceeds the supported calendar range") from exc


def _account_context(
    snapshot: DashboardSnapshot,
    *,
    symbol: str,
    policy: RadarPolicy,
    released_call_contracts: int = 0,
) -> RadarAccountContext:
    live_underlying = None
    if snapshot.live_position_book is not None:
        live_underlying = next(
            (item for item in snapshot.live_position_book.underlyings if item.symbol == symbol),
            None,
        )
    summary_underlying = next(
        (item for item in snapshot.underlyings if item.symbol == symbol),
        None,
    )
    shares = (
        live_underlying.shares
        if live_underlying is not None
        else summary_underlying.shares
        if summary_underlying is not None
        else 0
    )
    capacity = (
        live_underlying.contract_capacity
        if live_underlying is not None
        else summary_underlying.contract_capacity
        if summary_underlying is not None
        else max(0, shares // 100)
    )
    open_calls = (
        live_underlying.open_call_contracts
        if live_underlying is not None
        else summary_underlying.active_contracts
        if summary_underlying is not None
        else 0
    )
    return RadarAccountContext(
        shares=shares,
        covered_call_contracts=open_calls,
        available_call_lots=max(0, capacity - open_calls + released_call_contracts),
        reserved_cash=policy.reserved_cash,
        account_mask=(str(snapshot.accounts[0].get("account_mask")) if snapshot.accounts else None),
    )


def _resolve_roll_source(
    snapshot: DashboardSnapshot,
    *,
    symbol: str,
    mode: RadarMode,
    request: RadarRollRequest | None,
) -> OpenCallClock | None:
    if request is None:
        return None
    if mode is not RadarMode.COVERED_CALL:
        raise RadarRollRequestError("Roll review is available only for an open covered call.")
    underlying = next((item for item in snapshot.underlyings if item.symbol == symbol), None)
    source = next(
        (
            call
            for call in (underlying.open_call_clocks if underlying is not None else ())
            if call.record_id == request.source_option_symbol
        ),
        None,
    )
    if source is None:
        raise RadarRollRequestError(
            "That source call is no longer open. Refresh the desk before reviewing a roll."
        )
    if request.target_expiration <= source.expires_on or request.target_strike <= source.strike:
        raise RadarRollRequestError(
            "A roll-up review requires a later expiration and a higher strike."
        )
    return source


def _build_roll_review(
    projection: RadarProjection,
    *,
    bundle: RadarMarketBundle,
    source: OpenCallClock,
    request: RadarRollRequest,
) -> RadarRollReview:
    target = next(
        (
            candidate
            for candidate in projection.candidates
            if candidate.expiration_date == request.target_expiration
            and candidate.strike == request.target_strike
        ),
        None,
    )
    refreshed_source = _find_source_contract(bundle, source)
    source_ask = _source_close_ask(bundle, source)
    source_quote_status = (
        "fresh_chain"
        if refreshed_source is not None
        and refreshed_source.ask is not None
        and refreshed_source.ask > 0
        else "desk_snapshot"
    )
    target_bid = target.bid if target is not None else None
    net_per_share = target_bid - source_ask if target_bid is not None else None
    contract_shares = Decimal(source.contracts * 100)
    comparisons = tuple(
        RadarRollComparison(
            option_symbol=candidate.option_symbol,
            expiration_date=candidate.expiration_date,
            strike=candidate.strike,
            bid_per_share=candidate.bid,
            net_roll_per_share=candidate.bid - source_ask,
            net_roll_cash=(candidate.bid - source_ask) * contract_shares,
            strike_change_per_share=candidate.strike - source.strike,
            added_days=(candidate.expiration_date - source.expires_on).days,
        )
        for candidate in projection.candidates
    )
    return RadarRollReview(
        source_option_symbol=source.record_id,
        source_expiration_date=source.expires_on,
        source_strike=source.strike,
        source_contracts=source.contracts,
        source_close_ask_per_share=source_ask,
        source_quote_status=source_quote_status,
        target_expiration_date=request.target_expiration,
        target_strike=request.target_strike,
        target_bid_per_share=target_bid,
        net_roll_per_share=net_per_share,
        net_roll_cash=(net_per_share * contract_shares if net_per_share is not None else None),
        strike_lift_per_share=request.target_strike - source.strike,
        added_days=(request.target_expiration - source.expires_on).days,
        status="matched" if target is not None else "unavailable",
        comparisons=comparisons,
    )


def _roll_selection_context(
    bundle: RadarMarketBundle,
    source: OpenCallClock,
) -> RadarRollSelectionContext:
    return RadarRollSelectionContext(
        source_expiration_date=source.expires_on,
        source_strike=source.strike,
        source_close_ask_per_share=_source_close_ask(bundle, source),
    )


def _source_close_ask(
    bundle: RadarMarketBundle,
    source: OpenCallClock,
) -> Decimal:
    refreshed_source = _find_source_contract(bundle, source)
    if (
        refreshed_source is not None
        and refreshed_source.ask is not None
        and refreshed_source.ask > 0
    ):
        return refreshed_source.ask
    return source.close_ask_per_share


def _find_source_contract(
    bundle: RadarMarketBundle,
    source: OpenCallClock,
) -> RadarMarketContract | None:
    exact = next(
        (contract for contract in bundle.contracts if contract.option_symbol == source.record_id),
        None,
    )
    if exact is not None:
        return exact
    return next(
        (
            contract
            for contract in bundle.contracts
            if contract.option_side is RadarMode.COVERED_CALL.option_side
            and contract.expiration_date == source.expires_on
            and contract.strike == source.strike
        ),
        None,
    )


def _safe_error_message(error: Exception, *, state: str) -> str:
    if isinstance(error, RadarRollRequestError):
        return str(error)
    if state == "authorization_required":
        return "The selected Schwab connection needs authorization before Radar can load a chain."
    if state == "unsupported":
        return "Schwab did not return a supported option chain for that ticker and date range."
    if isinstance(error, httpx.TimeoutException):
        return (
            "Schwab did not answer the Radar lookup in time. "
            "Your normal account sync is unaffected."
        )
    return "Radar could not complete this lookup. The normal account sync is unaffected."
