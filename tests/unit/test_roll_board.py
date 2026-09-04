from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

from schwab_dashboard.application.dashboard.covered_calls import RollQuoteCandidate
from schwab_dashboard.application.dashboard.models import (
    LiveOpenOptionPosition,
    LivePositionBook,
)
from schwab_dashboard.application.market_time import OptionSessionState
from schwab_dashboard.application.rolls import RollQuote
from schwab_dashboard.application.rolls.board import build_roll_board
from schwab_dashboard.application.rolls.catalog import build_roll_source_catalog
from schwab_dashboard.domain.instruments import OptionSide
from schwab_dashboard.infrastructure.demo.dashboard import DemoDashboardReader

D = Decimal


def test_roll_board_ranks_an_urgent_call_and_exposes_candidates() -> None:
    snapshot = DemoDashboardReader().execute()
    underlying = snapshot.underlyings[0]
    call = underlying.open_call_clocks[0]
    urgent = replace(
        call,
        days_to_expiration=2,
        strike_distance_per_share=D("-1"),
        strike_distance_percent=D("-1.5"),
        close_ask_per_share=D("1.25"),
        roll_quote_candidates=(
            RollQuoteCandidate(
                option_symbol="NEXT CALL",
                expires_on=call.expires_on + timedelta(days=7),
                strike=call.strike + D("5"),
                sell_bid_per_share=D("1.20"),
                quote_source="TEST",
            ),
        ),
    )
    updated = replace(underlying, open_call_clocks=(urgent, *underlying.open_call_clocks[1:]))
    projection = build_roll_board(
        replace(snapshot, underlyings=(updated, *snapshot.underlyings[1:]))
    )

    row = next(item for item in projection.rows if item.source.option_symbol == call.record_id)
    assert row.anchor_id.startswith("roll-option-")
    assert row.days_to_expiration == 2
    assert row.urgency == "NEEDS ATTENTION"
    assert row.candidates[0].option_symbol == "NEXT CALL"
    assert projection.total_contracts == sum(item.source.contracts for item in projection.rows)
    assert projection.posture == "AT THE DESK"


def test_roll_board_separates_premium_scale_from_known_share_delivery() -> None:
    snapshot = DemoDashboardReader().execute()
    underlying = snapshot.underlyings[0]
    source = underlying.open_call_clocks[0]
    adjusted = replace(
        source,
        contracts=2,
        contract_multiplier=D("150"),
        days_to_expiration=2,
        strike_distance_per_share=D("-1"),
        strike_distance_percent=D("-1"),
        close_ask_per_share=D("1"),
        roll_quote_candidates=(
            RollQuoteCandidate(
                option_symbol="ADJUSTED NEXT",
                expires_on=source.expires_on + timedelta(days=7),
                strike=source.strike + D("5"),
                sell_bid_per_share=D("1.50"),
                quote_source="TEST",
            ),
        ),
    )
    projection = build_roll_board(
        replace(snapshot, underlyings=(replace(underlying, open_call_clocks=(adjusted,)),))
    )
    row = projection.rows[0]

    assert row.source.contract_multiplier == D("150")
    assert row.assignment_notional == source.strike * D("200")
    assert row.candidates[0].net_roll_cash == D("150")


def test_roll_board_withholds_comparison_when_share_delivery_is_unresolved() -> None:
    snapshot = DemoDashboardReader().execute()
    underlying = snapshot.underlyings[0]
    source = replace(
        underlying.open_call_clocks[0],
        days_to_expiration=2,
        strike_distance_per_share=D("-1"),
        strike_distance_percent=D("-1"),
        deliverable_shares_per_contract=None,
    )

    projection = build_roll_board(
        replace(snapshot, underlyings=(replace(underlying, open_call_clocks=(source,)),))
    )
    row = projection.rows[0]

    assert row.assignment_notional is None
    assert projection.total_assignment_notional is None
    assert row.candidates == ()
    assert row.no_clean_reason is not None
    assert "adjusted or unresolved deliverable" in row.no_clean_reason


def test_roll_board_handles_short_puts_and_names_missing_market_data() -> None:
    snapshot = DemoDashboardReader().execute()
    expires_on = date(2026, 8, 15)
    put = LiveOpenOptionPosition(
        account_mask="...1234",
        option_symbol="KTOS PUT",
        underlying_symbol="KTOS",
        contracts=1,
        expires_on=expires_on,
        days_to_expiration=2,
        strike=D("65"),
        entry_credit_per_share=D("2"),
        estimated_mark_per_share=D("2.5"),
        market_value=D("-250"),
        open_profit_loss=D("-50"),
        day_profit_loss=D("-20"),
        underlying_price=D("64"),
        strike_distance_per_share=D("-1"),
        strike_distance_percent=D("-1.56"),
        ask_per_share=D("2.6"),
        option_type="PUT",
        roll_quote_candidates=(
            RollQuote(
                option_symbol="KTOS NEXT PUT",
                expires_on=expires_on + timedelta(days=14),
                strike=D("60"),
                sell_bid_per_share=D("2.4"),
                quote_source="TEST",
            ),
        ),
    )
    book = LivePositionBook(
        underlyings=(),
        calls=(),
        total_shares=0,
        contract_capacity=0,
        open_call_positions=0,
        open_call_contracts=0,
        covered_contracts=0,
        uncovered_contracts=0,
        coverage_percent=D("0"),
        open_mark_profit_loss=D("0"),
        puts=(put,),
        open_put_positions=1,
        open_put_contracts=1,
    )

    projection = build_roll_board(replace(snapshot, underlyings=(), live_position_book=book))

    assert projection.rows[0].source.option_symbol == "KTOS PUT"
    assert projection.rows[0].anchor_id == "roll-option-ktos-put"
    assert projection.rows[0].candidates[0].strike == D("60")
    assert projection.posture == "AT THE DESK"


def test_roll_board_uses_data_fog_when_no_roll_math_can_be_verified() -> None:
    snapshot = DemoDashboardReader().execute()
    fogged = tuple(
        replace(
            underlying,
            open_call_clocks=tuple(
                replace(call, roll_quote_candidates=()) for call in underlying.open_call_clocks
            ),
        )
        for underlying in snapshot.underlyings
    )

    projection = build_roll_board(replace(snapshot, underlyings=fogged))

    assert projection.rows
    assert projection.no_clean_count == len(projection.rows)
    assert projection.posture == "DATA FOG"


def test_roll_board_withholds_cash_math_when_call_ask_is_missing() -> None:
    snapshot = DemoDashboardReader().execute()
    underlying = snapshot.underlyings[0]
    call = replace(
        underlying.open_call_clocks[0],
        days_to_expiration=2,
        strike_distance_per_share=D("-1"),
        strike_distance_percent=D("-1"),
        close_ask_per_share=None,
    )
    updated = replace(underlying, open_call_clocks=(call,))

    projection = build_roll_board(
        replace(snapshot, underlyings=(updated, *snapshot.underlyings[1:]))
    )
    row = next(item for item in projection.rows if item.source.option_symbol == call.record_id)

    assert row.candidates == ()
    assert row.no_clean_reason is not None
    assert "ask is unavailable" in row.no_clean_reason


def test_roll_board_demo_call_replacements_move_up_and_out() -> None:
    projection = build_roll_board(DemoDashboardReader().execute())
    call_rows = [row for row in projection.rows if row.source.option_side is OptionSide.CALL]

    assert call_rows
    for row in call_rows:
        assert row.candidates
        assert all(item.strike > row.source.strike for item in row.candidates)
        assert all(item.expires_on > row.source.expires_on for item in row.candidates)
        assert len(row.candidates) > 2
        assert len({item.expires_on for item in row.candidates}) >= 2
        assert all(item.family_label != "LOWEST CASH COST" for item in row.candidates)


def test_radar_roll_catalog_includes_every_open_call_without_requiring_an_alert() -> None:
    snapshot = DemoDashboardReader().execute()

    catalog = build_roll_source_catalog(snapshot)

    expected_calls = sum(len(underlying.open_call_clocks) for underlying in snapshot.underlyings)
    assert len(catalog) == expected_calls
    assert {choice.option_side for choice in catalog} == {OptionSide.CALL}
    assert {choice.symbol for choice in catalog} == {"CVX", "KTOS", "URNM"}


def test_roll_board_excludes_broker_inventory_after_the_last_trading_session() -> None:
    snapshot = DemoDashboardReader().execute()
    underlying = snapshot.underlyings[0]
    call = replace(
        underlying.open_call_clocks[0],
        session_state=OptionSessionState.CLOSED_PENDING_SETTLEMENT,
    )
    updated = replace(
        underlying,
        open_call_clocks=(call, *underlying.open_call_clocks[1:]),
    )

    projection = build_roll_board(
        replace(snapshot, underlyings=(updated, *snapshot.underlyings[1:]))
    )

    assert call.record_id not in {row.source.option_symbol for row in projection.rows}
    assert call.record_id not in {
        choice.option_symbol
        for choice in build_roll_source_catalog(
            replace(snapshot, underlyings=(updated, *snapshot.underlyings[1:]))
        )
    }
