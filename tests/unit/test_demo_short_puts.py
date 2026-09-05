from dataclasses import replace
from datetime import date
from decimal import Decimal

from schwab_dashboard.application.dashboard.live_campaigns import project_campaign_summaries
from schwab_dashboard.application.dashboard.open_put_clocks import build_open_put_clocks
from schwab_dashboard.application.dashboard.overview import build_desk_overview
from schwab_dashboard.application.dashboard.premium_pace import build_open_premium_pace
from schwab_dashboard.application.risk.projection import build_open_risk_summary
from schwab_dashboard.application.rolls.board import build_roll_board
from schwab_dashboard.application.workspaces.projections import build_open_book
from schwab_dashboard.domain.analytics import DataQuality
from schwab_dashboard.domain.instruments import OptionSide
from schwab_dashboard.infrastructure.demo.dashboard import DemoDashboardReader
from schwab_dashboard.infrastructure.demo.fixtures.call_history import build_call_history
from schwab_dashboard.infrastructure.demo.fixtures.position_book import (
    build_demo_opening_executions,
    build_demo_position_book,
)
from schwab_dashboard.infrastructure.demo.fixtures.positions import build_positions
from schwab_dashboard.infrastructure.demo.fixtures.short_puts import (
    build_put_cash_activity_items,
    build_put_cash_events,
    build_put_executions,
)

D = Decimal
AS_OF = date(2026, 8, 7)


def test_demo_puts_have_cash_collateral_and_reconciled_liabilities() -> None:
    puts = tuple(item for item in build_positions() if item.option_type == "PUT")

    assert len(puts) == 2
    assert sum(abs(item.quantity) * item.strike * 100 for item in puts) == D("11500")
    assert D("18750") - sum(abs(item.quantity) * item.strike * 100 for item in puts) == D("7250")
    assert sum(item.market_value for item in puts) == D("-495")
    assert sum(item.open_profit_loss for item in puts) == D("95")
    for put in puts:
        assert put.market_value == put.quantity * put.mark * put.contract_multiplier
        assert put.open_profit_loss == abs(put.quantity) * (put.average_price - put.mark) * 100


def test_demo_open_book_uses_production_terms_for_calls_and_puts() -> None:
    records = build_call_history()
    book = build_demo_position_book(build_positions(), records, as_of=AS_OF)
    pace = build_open_premium_pace(book, build_demo_opening_executions(records))
    campaigns = project_campaign_summaries(build_put_executions(), (), live_book=book, as_of=AS_OF)
    clocks = build_open_put_clocks(book.puts, campaigns=campaigns)

    assert book.open_call_contracts == 18
    assert book.open_put_contracts == 2
    assert book.uncovered_contracts == 0
    assert not book.unmodeled_short_options
    assert pace.total_contracts == pace.timed_contracts == 20
    assert pace.opening_credit == D("3980")
    assert all(option.opened_on is not None for option in book.options)
    assert all(clock.campaign_id and clock.campaign_label == "P1" for clock in clocks)
    assert sum(campaign.collateral for campaign in campaigns) == D("11500")


def test_demo_risk_models_both_option_sides_without_missing_greeks() -> None:
    snapshot = DemoDashboardReader().execute()
    book = build_demo_position_book(snapshot.positions, snapshot.call_history, as_of=AS_OF)
    risk = build_open_risk_summary(replace(snapshot, live_position_book=book))

    assert risk is not None
    assert risk.context.quality is DataQuality.COMPLETE
    assert risk.delta_coverage_percent == risk.theta_coverage_percent == D("100")
    assert risk.gamma_coverage_percent == risk.vega_coverage_percent == D("100")
    assert risk.quote_coverage_percent == D("100")
    assert risk.option_delta_share_equivalent == D("-219")
    assert risk.net_delta_share_equivalent == D("1781")
    assert risk.theta_estimate_per_day == D("83.9")
    assert all(put.position_delta_share_equivalent > 0 for put in book.puts)


def test_demo_put_rolls_include_cash_credit_and_protective_strike_choices() -> None:
    snapshot = DemoDashboardReader().execute()
    book = build_demo_position_book(snapshot.positions, snapshot.call_history, as_of=AS_OF)
    board = build_roll_board(replace(snapshot, live_position_book=book))
    put_rows = tuple(row for row in board.rows if row.source.option_side is OptionSide.PUT)

    assert len(put_rows) == 2
    assert {row.symbol for row in put_rows} == {"KTOS", "URNM"}
    for row in put_rows:
        assert len(row.candidates) == 9
        assert any(item.assignment_room_gain > 0 for item in row.candidates)
        assert any(item.net_roll_cash > 0 for item in row.candidates)
        assert any(item.net_roll_cash < 0 for item in row.candidates)
        for item in row.candidates:
            assert item.quote_source == "SIMULATED BID"
            assert item.strike <= row.source.strike
            assert item.expires_on > row.source.expires_on
            assert (
                item.net_roll_cash
                == (item.sell_bid_per_share - row.source.close_ask_per_share) * 100
            )


def test_demo_put_cash_is_opening_credit_without_mark_profit() -> None:
    events = build_put_cash_events()
    activity = build_put_cash_activity_items()

    assert sum(event.amount for event in events) == D("590")
    assert {event.occurred_on for event in events} == {date(2026, 8, 3), date(2026, 8, 4)}
    assert all(item.action_label == "PUT SOLD" for item in activity)
    assert sum(item.amount for item in activity) == D("590")


def test_demo_roll_history_closes_prior_leg_before_opening_its_replacement() -> None:
    records = build_call_history()
    by_id = {record.record_id: record for record in records}

    for record in records:
        if record.parent_record_id is None:
            continue
        previous = by_id[record.parent_record_id]
        assert previous.outcome == "Rolled"
        assert previous.closed_on is not None
        assert previous.closed_on <= record.sold_on


def test_demo_adapter_exposes_puts_in_name_and_options_views() -> None:
    snapshot = DemoDashboardReader().execute()
    overview = build_desk_overview(snapshot)
    options = build_open_book(snapshot)

    assert snapshot.live_position_book is not None
    assert snapshot.option_outcomes.open_put_contracts == 2
    assert snapshot.risk.short_contracts == 20
    assert sum(row.open_put_contracts for row in overview.position_rows) == 2
    assert sum(len(row.put_clocks) for row in overview.position_rows) == 2
    assert len(options.put_rows) == 2
    assert snapshot.risk.daily_theta == D("83.9")
    assert snapshot.risk.portfolio_delta == D("1781")
