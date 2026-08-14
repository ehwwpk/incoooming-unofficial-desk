from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from schwab_dashboard.application.opportunities import evaluate_radar
from schwab_dashboard.application.opportunities.eligibility import evaluate_gates
from schwab_dashboard.application.opportunities.quote_math import (
    bid_credit_per_calendar_day,
    expected_move,
    simple_annualized_rate,
    spread_percent,
)
from schwab_dashboard.domain.opportunity import (
    RadarAccountContext,
    RadarGateStatus,
    RadarMode,
    RadarPolicy,
    RadarState,
)
from schwab_dashboard.infrastructure.demo.opportunity import DemoOpportunityMarketGateway

NOW = datetime(2026, 8, 11, 18, tzinfo=UTC)


def test_radar_policy_defaults_are_preferences_not_capability_limits() -> None:
    policy = RadarPolicy(
        symbol="SPY",
        mode=RadarMode.COVERED_CALL,
        minimum_dte=0,
        maximum_dte=1095,
        minimum_annualized_rate_percent=Decimal("0"),
    )

    assert policy.minimum_dte == 0
    assert policy.maximum_dte == 1095
    assert policy.minimum_annualized_rate_percent == Decimal("0")
    assert policy.maximum_spread_percent is None
    assert policy.maximum_five_day_move_percent is None


def test_quote_math_is_bid_based_and_does_not_hide_a_wide_market() -> None:
    assert spread_percent(Decimal("1.00"), Decimal("1.50")) == Decimal("40")
    assert simple_annualized_rate(
        premium_per_share=Decimal("1.20"),
        capital_per_share=Decimal("60"),
        dte=30,
    ).quantize(Decimal("0.01")) == Decimal("24.33")
    assert expected_move(Decimal("100"), Decimal("36"), 30) is not None
    assert bid_credit_per_calendar_day(
        premium_per_contract=Decimal("220"),
        dte=30,
    ).quantize(Decimal("0.01")) == Decimal("7.33")


def test_optional_spread_limit_does_not_weaken_quote_validation() -> None:
    bundle = DemoOpportunityMarketGateway().fetch(
        symbol="URNM",
        mode=RadarMode.CASH_SECURED_PUT,
        from_date=NOW.date(),
        to_date=NOW.date(),
    )
    contract = replace(bundle.contracts[0], ask=Decimal("9.80"))
    policy = RadarPolicy(
        symbol="URNM",
        mode=RadarMode.CASH_SECURED_PUT,
        reserved_cash=Decimal("100000"),
    )
    account = RadarAccountContext(
        shares=0,
        covered_call_contracts=0,
        available_call_lots=0,
        reserved_cash=Decimal("100000"),
    )
    spot = bundle.underlying_price
    assert spot is not None
    spread = next(
        gate
        for gate in evaluate_gates(
            contract,
            mode=RadarMode.CASH_SECURED_PUT,
            policy=policy,
            account=account,
            spot=spot,
            dte=(contract.expiration_date - NOW.date()).days,
            five_day_move_percent=None,
            now=NOW,
        )
        if gate.code == "spread"
    )
    missing_market = replace(contract, bid=None)
    invalid_spread = next(
        gate
        for gate in evaluate_gates(
            missing_market,
            mode=RadarMode.CASH_SECURED_PUT,
            policy=policy,
            account=account,
            spot=spot,
            dte=(contract.expiration_date - NOW.date()).days,
            five_day_move_percent=None,
            now=NOW,
        )
        if gate.code == "spread"
    )

    assert spread.status is RadarGateStatus.PASS
    assert spread.detail == "No bid/ask width limit is configured"
    assert invalid_spread.status is RadarGateStatus.FAIL


def test_covered_call_radar_returns_only_candidates_that_clear_account_and_policy() -> None:
    bundle = DemoOpportunityMarketGateway().fetch(
        symbol="KTOS",
        mode=RadarMode.COVERED_CALL,
        from_date=NOW.date(),
        to_date=NOW.date(),
    )
    projection = evaluate_radar(
        lookup_id="lookup-1",
        bundle=bundle,
        mode=RadarMode.COVERED_CALL,
        account=RadarAccountContext(
            shares=1000,
            covered_call_contracts=8,
            available_call_lots=2,
            reserved_cash=Decimal("0"),
        ),
        policy=RadarPolicy(
            symbol="KTOS",
            mode=RadarMode.COVERED_CALL,
            minimum_dte=14,
            maximum_dte=60,
            minimum_strike=Decimal("70"),
            allowed_contracts=1,
        ),
        now=NOW,
    )

    assert projection.state is RadarState.PARTIAL
    assert projection.candidates
    assert len(projection.candidates) <= 9
    assert all(
        candidate.simple_annualized_rate_percent >= Decimal("5")
        for candidate in projection.candidates
    )
    assert all(candidate.strike >= Decimal("70") for candidate in projection.candidates)
    assert all(
        candidate.premium_dollars == candidate.bid * 100 for candidate in projection.candidates
    )
    assert all(candidate.eligible_contracts == 1 for candidate in projection.candidates)
    assert all(
        candidate.bid_credit_per_calendar_day
        == candidate.premium_per_contract / Decimal(candidate.days_to_expiration)
        for candidate in projection.candidates
    )
    assert projection.expiration_map is not None
    assert projection.expiration_map.spot == bundle.underlying_price
    assert len(projection.expiration_map.candidates) == len(projection.candidates)
    assert all(point.trade_date <= NOW.date() for point in projection.expiration_map.price_points)
    assert len(projection.expiration_map.indicator_points) == len(
        projection.expiration_map.price_points
    )
    assert projection.expiration_map.indicator_points[-1].rsi_14 is not None
    assert projection.expiration_map.indicator_points[-1].macd is not None
    assert projection.expiration_map.indicator_points[-1].macd_signal is not None
    assert projection.expiration_map.indicator_points[-1].macd_histogram is not None
    assert all(
        Decimal("0") <= candidate.y_percent <= Decimal("100")
        for candidate in projection.expiration_map.candidates
    )


def test_explicit_roll_target_remains_visible_when_normal_research_filters_reject_it() -> None:
    bundle = DemoOpportunityMarketGateway().fetch(
        symbol="KTOS",
        mode=RadarMode.COVERED_CALL,
        from_date=NOW.date(),
        to_date=NOW.date(),
    )
    target = next(
        contract
        for contract in bundle.contracts
        if contract.option_side is RadarMode.COVERED_CALL.option_side
    )

    projection = evaluate_radar(
        lookup_id="roll-review",
        bundle=bundle,
        mode=RadarMode.COVERED_CALL,
        account=RadarAccountContext(
            shares=1000,
            covered_call_contracts=10,
            available_call_lots=0,
            reserved_cash=Decimal("0"),
        ),
        policy=RadarPolicy(
            symbol="KTOS",
            mode=RadarMode.COVERED_CALL,
            minimum_dte=5,
            maximum_dte=60,
            minimum_strike=Decimal("9999"),
            allowed_contracts=1,
        ),
        now=NOW,
        preferred_strike=target.strike,
        preferred_expiration=target.expiration_date,
    )

    reviewed = next(
        candidate
        for candidate in projection.candidates
        if candidate.strike == target.strike and candidate.expiration_date == target.expiration_date
    )
    assert not reviewed.clears_all_rules
    assert any(gate.code == "minimum_strike" for gate in reviewed.gates)


def test_cash_secured_put_radar_shows_research_rows_until_setup_is_explicit() -> None:
    bundle = DemoOpportunityMarketGateway().fetch(
        symbol="URNM",
        mode=RadarMode.CASH_SECURED_PUT,
        from_date=NOW.date(),
        to_date=NOW.date(),
    )
    projection = evaluate_radar(
        lookup_id="lookup-2",
        bundle=bundle,
        mode=RadarMode.CASH_SECURED_PUT,
        account=RadarAccountContext(
            shares=500,
            covered_call_contracts=5,
            available_call_lots=0,
            reserved_cash=Decimal("0"),
        ),
        policy=RadarPolicy(
            symbol="URNM",
            mode=RadarMode.CASH_SECURED_PUT,
            reserved_cash=Decimal("0"),
            maximum_effective_entry=None,
        ),
        now=NOW,
    )

    assert projection.state is RadarState.WAIT
    assert projection.candidates
    assert all(not candidate.clears_all_rules for candidate in projection.candidates)
    assert all(candidate.eligible_contracts == 0 for candidate in projection.candidates)
    assert all(candidate.premium_per_contract > 0 for candidate in projection.candidates)
    assert any(
        "effective" in reason.lower() or "purchase price" in reason.lower()
        for reason in projection.reasons
    )
    assert any("cash" in reason.lower() for reason in projection.reasons)
    assert projection.expiration_map is not None
    assert all(
        candidate.effective_entry is not None and candidate.effective_entry_y_percent is not None
        for candidate in projection.expiration_map.candidates
    )


def test_cash_secured_put_minimum_discount_rejects_near_spot_strikes() -> None:
    bundle = DemoOpportunityMarketGateway().fetch(
        symbol="URNM",
        mode=RadarMode.CASH_SECURED_PUT,
        from_date=NOW.date(),
        to_date=NOW.date(),
    )
    projection = evaluate_radar(
        lookup_id="lookup-put-discount",
        bundle=bundle,
        mode=RadarMode.CASH_SECURED_PUT,
        account=RadarAccountContext(
            shares=500,
            covered_call_contracts=5,
            available_call_lots=0,
            reserved_cash=Decimal("100000"),
        ),
        policy=RadarPolicy(
            symbol="URNM",
            mode=RadarMode.CASH_SECURED_PUT,
            minimum_strike_distance_percent=Decimal("5"),
            reserved_cash=Decimal("100000"),
            maximum_effective_entry=Decimal("55"),
        ),
        now=NOW,
    )

    assert projection.candidates
    assert all(candidate.room_percent >= Decimal("5") for candidate in projection.candidates)
    assert all(
        any(
            gate.code == "strike_distance" and gate.status.value == "pass"
            for gate in candidate.gates
        )
        for candidate in projection.candidates
    )


def test_put_with_a_spread_beyond_the_saved_limit_is_not_promoted() -> None:
    bundle = DemoOpportunityMarketGateway().fetch(
        symbol="URNM",
        mode=RadarMode.CASH_SECURED_PUT,
        from_date=NOW.date(),
        to_date=NOW.date(),
    )
    projection = evaluate_radar(
        lookup_id="lookup-put-wide-market",
        bundle=bundle,
        mode=RadarMode.CASH_SECURED_PUT,
        account=RadarAccountContext(
            shares=500,
            covered_call_contracts=5,
            available_call_lots=0,
            reserved_cash=Decimal("100000"),
        ),
        policy=RadarPolicy(
            symbol="URNM",
            mode=RadarMode.CASH_SECURED_PUT,
            minimum_strike_distance_percent=Decimal("5"),
            maximum_spread_percent=Decimal("1"),
            reserved_cash=Decimal("100000"),
            maximum_effective_entry=Decimal("55"),
        ),
        now=NOW,
    )

    assert projection.state is RadarState.WAIT
    assert not projection.candidates
    assert projection.rejected_count > 0
    assert projection.headline == ("URNM chain loaded; no contract clears the current filters")
    assert any("chain returned contracts" in reason.lower() for reason in projection.reasons)


def test_empty_etf_chain_is_distinct_from_a_loaded_chain_filtered_to_zero() -> None:
    bundle = DemoOpportunityMarketGateway().fetch(
        symbol="URNM",
        mode=RadarMode.CASH_SECURED_PUT,
        from_date=NOW.date(),
        to_date=NOW.date(),
    )
    projection = evaluate_radar(
        lookup_id="lookup-empty-etf-chain",
        bundle=replace(bundle, contracts=()),
        mode=RadarMode.CASH_SECURED_PUT,
        account=RadarAccountContext(
            shares=500,
            covered_call_contracts=5,
            available_call_lots=0,
            reserved_cash=Decimal("100000"),
        ),
        policy=RadarPolicy(
            symbol="URNM",
            mode=RadarMode.CASH_SECURED_PUT,
            reserved_cash=Decimal("100000"),
            maximum_effective_entry=Decimal("55"),
        ),
        now=NOW,
    )

    assert projection.state is RadarState.WAIT
    assert not projection.candidates
    assert projection.headline == "No supported put contracts returned for URNM"
    assert any(
        "source returned no supported contracts" in reason.lower() for reason in projection.reasons
    )


def test_covered_call_radar_keeps_market_comparisons_when_no_lot_is_free() -> None:
    bundle = DemoOpportunityMarketGateway().fetch(
        symbol="CVX",
        mode=RadarMode.COVERED_CALL,
        from_date=NOW.date(),
        to_date=NOW.date(),
    )
    projection = evaluate_radar(
        lookup_id="lookup-3",
        bundle=bundle,
        mode=RadarMode.COVERED_CALL,
        account=RadarAccountContext(
            shares=100,
            covered_call_contracts=1,
            available_call_lots=0,
            reserved_cash=Decimal("0"),
        ),
        policy=RadarPolicy(symbol="CVX", mode=RadarMode.COVERED_CALL),
        now=NOW,
    )

    assert projection.state is RadarState.WAIT
    assert "no uncovered share lot" in projection.headline.lower()
    assert projection.candidates
    assert all(not candidate.clears_all_rules for candidate in projection.candidates)
    assert all(candidate.eligible_contracts == 0 for candidate in projection.candidates)


def test_radar_returns_at_most_three_iv_aware_choices_per_dte_horizon() -> None:
    base = DemoOpportunityMarketGateway().fetch(
        symbol="KTOS",
        mode=RadarMode.COVERED_CALL,
        from_date=NOW.date(),
        to_date=NOW.date(),
    )
    template = base.contracts[0]
    contracts = []
    for horizon_index, dte in enumerate((10, 30, 50)):
        for strike_index in range(4):
            bid = Decimal("1.20") + Decimal(strike_index) * Decimal("0.15")
            strike = Decimal("68") + Decimal(horizon_index * 4 + strike_index * 2)
            contracts.append(
                replace(
                    template,
                    option_symbol=f"KTOS-{dte}-{strike_index}",
                    expiration_date=NOW.date() + timedelta(days=dte),
                    strike=strike,
                    bid=bid,
                    ask=bid + Decimal("0.08"),
                    mark=bid + Decimal("0.04"),
                    implied_volatility=Decimal("55") + Decimal(horizon_index * 8),
                    open_interest=100 + strike_index * 100,
                    volume=20 + strike_index * 10,
                )
            )
    bundle = replace(base, contracts=tuple(contracts), observed_at=NOW)

    projection = evaluate_radar(
        lookup_id="lookup-diversified-nine",
        bundle=bundle,
        mode=RadarMode.COVERED_CALL,
        account=RadarAccountContext(
            shares=1000,
            covered_call_contracts=0,
            available_call_lots=10,
            reserved_cash=Decimal("0"),
        ),
        policy=RadarPolicy(
            symbol="KTOS",
            mode=RadarMode.COVERED_CALL,
            allowed_contracts=10,
        ),
        now=NOW,
    )

    assert len(projection.candidates) == 9
    assert all(
        candidate.simple_annualized_rate_percent >= Decimal("5")
        for candidate in projection.candidates
    )
    for minimum, maximum in ((5, 20), (21, 40), (41, 60)):
        horizon = [
            candidate
            for candidate in projection.candidates
            if minimum <= candidate.days_to_expiration <= maximum
        ]
        assert len(horizon) == 3
        assert len({candidate.option_symbol for candidate in horizon}) == 3


def test_radar_frontier_keeps_listed_long_dated_contracts() -> None:
    base = DemoOpportunityMarketGateway().fetch(
        symbol="KTOS",
        mode=RadarMode.COVERED_CALL,
        from_date=NOW.date(),
        to_date=NOW.date() + timedelta(days=365),
    )
    template = base.contracts[0]
    contracts = tuple(
        replace(
            template,
            option_symbol=f"KTOS-LONG-{dte}",
            expiration_date=NOW.date() + timedelta(days=dte),
            strike=Decimal("80") + Decimal(dte) / Decimal("100"),
            bid=Decimal("2.00"),
            ask=Decimal("2.08"),
            mark=Decimal("2.04"),
            observed_at=NOW,
            open_interest=500,
            volume=50,
        )
        for dte in (10, 45, 90, 365)
    )
    projection = evaluate_radar(
        lookup_id="lookup-long-dated",
        bundle=replace(base, contracts=contracts, observed_at=NOW),
        mode=RadarMode.COVERED_CALL,
        account=RadarAccountContext(
            shares=1000,
            covered_call_contracts=0,
            available_call_lots=10,
            reserved_cash=Decimal("0"),
        ),
        policy=RadarPolicy(
            symbol="KTOS",
            mode=RadarMode.COVERED_CALL,
            minimum_dte=0,
            maximum_dte=365,
            minimum_annualized_rate_percent=Decimal("0"),
            allowed_contracts=10,
        ),
        now=NOW,
    )

    assert any(candidate.days_to_expiration == 365 for candidate in projection.candidates)
    assert len(projection.candidates) <= 9


def test_radar_does_not_pad_a_horizon_with_sub_five_percent_contracts() -> None:
    bundle = DemoOpportunityMarketGateway().fetch(
        symbol="URNM",
        mode=RadarMode.CASH_SECURED_PUT,
        from_date=NOW.date(),
        to_date=NOW.date(),
    )
    weak = replace(
        bundle.contracts[-1],
        bid=Decimal("0.05"),
        ask=Decimal("0.06"),
        mark=Decimal("0.055"),
    )
    bundle = replace(bundle, contracts=(*bundle.contracts[:-1], weak))
    projection = evaluate_radar(
        lookup_id="lookup-rate-floor",
        bundle=bundle,
        mode=RadarMode.CASH_SECURED_PUT,
        account=RadarAccountContext(
            shares=500,
            covered_call_contracts=5,
            available_call_lots=0,
            reserved_cash=Decimal("100000"),
        ),
        policy=RadarPolicy(
            symbol="URNM",
            mode=RadarMode.CASH_SECURED_PUT,
            reserved_cash=Decimal("100000"),
            maximum_effective_entry=Decimal("55"),
        ),
        now=NOW,
    )

    assert projection.candidates
    assert len(projection.candidates) < 3
    assert projection.rejected_count > 0
    assert all(
        candidate.simple_annualized_rate_percent >= Decimal("5")
        for candidate in projection.candidates
    )
