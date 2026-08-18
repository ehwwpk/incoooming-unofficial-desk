from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from schwab_dashboard.application.opportunities.frontier import order_general_frontier
from schwab_dashboard.application.opportunities.roll_frontier import select_roll_frontier
from schwab_dashboard.domain.instruments import OptionSide
from schwab_dashboard.domain.opportunity import (
    RadarCandidate,
    RadarCandidateLabel,
    RadarMode,
    RadarRollSelectionContext,
)

D = Decimal
NOW = datetime(2026, 8, 13, 18, tzinfo=UTC)
SOURCE_EXPIRATION = date(2026, 8, 14)


def test_roll_frontier_uses_nearby_listed_calls_and_appends_preferred() -> None:
    context = RadarRollSelectionContext(
        option_side=OptionSide.CALL,
        source_expiration_date=SOURCE_EXPIRATION,
        source_strike=D("68"),
        source_close_ask_per_share=D("0.25"),
        source_current_price=D("63"),
    )
    nearby = (
        _candidate("w1-a", added_days=7, strike="70", bid="0.25"),
        _candidate("w1-b", added_days=7, strike="72.5", bid="0.20"),
        _candidate("w1-c", added_days=7, strike="73", bid="0.15"),
        _candidate("w2-a", added_days=14, strike="70", bid="0.35"),
        _candidate("w2-b", added_days=14, strike="72.5", bid="0.28"),
        _candidate("w2-c", added_days=14, strike="73", bid="0.22"),
        _candidate("w3-a", added_days=21, strike="70", bid="0.45"),
        _candidate("w3-b", added_days=21, strike="72.5", bid="0.36"),
        _candidate("w3-c", added_days=21, strike="73", bid="0.30"),
        _candidate("far", added_days=56, strike="100", bid="2.25"),
    )
    invalid = (
        _candidate("same-expiry", added_days=0, strike="75", bid="0.25"),
        _candidate("lower-strike", added_days=14, strike="65", bid="0.25"),
        _candidate("same-strike-date-push", added_days=7, strike="68", bid="0.25"),
    )
    preferred = nearby[-1]

    selected = select_roll_frontier(
        (*nearby, *invalid),
        context=context,
        preferred=preferred,
    )

    assert [item.option_symbol for item in selected[:3]] == ["w1-a", "w1-b", "w1-c"]
    assert selected[-1].option_symbol == "far"
    assert len(selected) == 10
    assert all(item.expiration_date > SOURCE_EXPIRATION for item in selected)
    assert all(item.strike > D("68") for item in selected)
    assert selected[0].label is RadarCandidateLabel.NEAR_FLAT
    assert selected[-1].label is RadarCandidateLabel.NET_CREDIT
    assert "LEAST EXTRA TIME" not in {item.label.value for item in selected if item.label}


def test_general_frontier_is_presented_by_time_then_protection() -> None:
    candidates = (
        _candidate("far-high", added_days=35, strike="80", bid="1.00"),
        _candidate("near-high", added_days=7, strike="75", bid="1.00"),
        _candidate("near-low", added_days=7, strike="70", bid="1.00"),
        _candidate("far-low", added_days=35, strike="72.5", bid="1.00"),
    )

    calls = order_general_frontier(candidates, mode=RadarMode.COVERED_CALL)
    puts = order_general_frontier(candidates, mode=RadarMode.CASH_SECURED_PUT)

    assert [item.option_symbol for item in calls] == [
        "near-low",
        "near-high",
        "far-low",
        "far-high",
    ]
    assert [item.option_symbol for item in puts] == [
        "near-high",
        "near-low",
        "far-high",
        "far-low",
    ]


def test_roll_frontier_supports_same_or_lower_puts() -> None:
    context = RadarRollSelectionContext(
        option_side=OptionSide.PUT,
        source_expiration_date=SOURCE_EXPIRATION,
        source_strike=D("60"),
        source_close_ask_per_share=D("1.00"),
    )
    selected = select_roll_frontier(
        (
            _candidate("same-put", added_days=7, strike="60", bid="1.00"),
            _candidate("lower-put", added_days=14, strike="56", bid="0.95"),
            _candidate("invalid-higher-put", added_days=7, strike="65", bid="1.50"),
        ),
        context=context,
    )

    assert [item.option_symbol for item in selected] == ["same-put", "lower-put"]
    assert selected[0].label is RadarCandidateLabel.NEAR_FLAT


def _candidate(
    symbol: str,
    *,
    added_days: int,
    strike: str,
    bid: str,
) -> RadarCandidate:
    bid_value = D(bid)
    strike_value = D(strike)
    expiration = SOURCE_EXPIRATION + timedelta(days=added_days)
    return RadarCandidate(
        option_symbol=symbol,
        label=None,
        strike=strike_value,
        expiration_date=expiration,
        days_to_expiration=(expiration - NOW.date()).days,
        bid=bid_value,
        ask=bid_value + D("0.05"),
        midpoint=bid_value + D("0.025"),
        spread_dollars=D("0.05"),
        spread_percent=D("5"),
        room_dollars=strike_value - D("63"),
        room_percent=D("10"),
        expected_move=D("5"),
        strike_distance_in_moves=D("1"),
        delta=D("0.25"),
        implied_volatility=D("55"),
        open_interest=500,
        volume=50,
        quote_observed_at=NOW,
        premium_per_contract=bid_value * D("100"),
        bid_credit_per_calendar_day=bid_value,
        premium_dollars=bid_value * D("100"),
        simple_annualized_rate_percent=D("10"),
        effective_entry=None,
        cash_required=None,
        eligible_contracts=1,
        clears_all_rules=True,
        gates=(),
        reasons=(),
    )
