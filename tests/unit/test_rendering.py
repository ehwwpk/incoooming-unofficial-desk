from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

from schwab_dashboard.application.dashboard.live_positions import build_live_position_book
from schwab_dashboard.application.dashboard.models import (
    LivePositionBook,
    LiveUnderlyingPosition,
    PositionSummary,
)
from schwab_dashboard.application.dashboard.overview import build_desk_overview
from schwab_dashboard.application.market_time import QuoteSession
from schwab_dashboard.application.rolls.board import build_roll_board
from schwab_dashboard.application.workspaces.projections import build_open_book
from schwab_dashboard.infrastructure.demo.dashboard import DemoDashboardReader
from schwab_dashboard.web.rendering import money, number, percent, pnl_class, templates


def test_financial_display_filters_are_consistent() -> None:
    assert money(Decimal("1234.5")) == "$1,234.50"
    assert money(Decimal("-42.25")) == "-$42.25"
    assert number(Decimal("12.25"), 1) == "12.2"
    assert percent(Decimal("4.236"), 2) == "4.24%"
    assert money(None) == "—"


def test_profit_loss_css_class_uses_numeric_sign() -> None:
    assert pnl_class(Decimal("1")) == "positive"
    assert pnl_class(Decimal("-1")) == "negative"
    assert pnl_class(Decimal("0")) == "muted"


def test_basis_lens_renders_positive_surplus_after_full_capital_recovery() -> None:
    snapshot = DemoDashboardReader().execute()
    portfolio_basis, *names = snapshot.basis_lens
    recovered_basis = replace(
        portfolio_basis,
        original_cost_basis=Decimal("100000"),
        lifetime_management_income=Decimal("127500"),
        income_adjusted_basis=Decimal("-27500"),
        basis_offset_percent=Decimal("127.5"),
        capital_remaining=Decimal("0"),
        recovery_surplus=Decimal("27500"),
        fully_recovered=True,
    )
    recovered_snapshot = replace(snapshot, basis_lens=(recovered_basis, *names))

    rendered = templates.env.get_template("workspaces/_strategy_review.html").render(
        snapshot=recovered_snapshot
    )

    assert "CASH BEYOND ORIGINAL COST" in rendered
    assert "+$27,500.00" in rendered


def test_campaign_charts_render_as_lazy_accessible_workspaces() -> None:
    snapshot = DemoDashboardReader().execute()
    overview = build_desk_overview(snapshot)

    rendered = templates.env.get_template("partials/_underlyings.html").render(
        snapshot=snapshot,
        desk_overview=overview,
    )

    assert rendered.count("data-campaign-chart data-symbol") == len(snapshot.underlyings)
    assert rendered.count("data-campaign-chart-fallback") == len(snapshot.underlyings)
    assert "data-campaign-chart-legacy" not in rendered
    assert rendered.count("data-campaign-focus") == len(snapshot.underlyings)
    assert rendered.count("data-campaign-chart-context") == len(snapshot.underlyings)
    assert rendered.count("data-campaign-rail") == len(snapshot.underlyings)
    assert rendered.count('role="group" aria-label="Market chart style"') == len(
        snapshot.underlyings
    )
    assert rendered.count('role="group" aria-label="Option campaign visibility"') == len(
        snapshot.underlyings
    )
    assert rendered.count('role="group" aria-label="Chart range"') == len(snapshot.underlyings)
    expected_option_cards = sum(
        len(row.underlying.open_call_clocks)
        + len(row.live_underlying.puts if row.live_underlying else ())
        for row in overview.position_rows
    )
    assert rendered.count("data-option-lifecycle") == expected_option_cards
    assert rendered.count('role="button"') >= expected_option_cards
    for item in snapshot.underlyings:
        for call in item.open_call_clocks:
            assert f'data-option-campaign="{call.campaign_id}"' in rendered
    assert overview.nearest_call is not None
    assert f'id="{overview.nearest_call.anchor_id}"' in rendered


def test_live_summary_deep_links_to_the_exact_nearest_contract() -> None:
    snapshot = DemoDashboardReader().execute()
    overview = build_desk_overview(snapshot)

    rendered = templates.env.get_template("partials/_summary.html").render(
        snapshot=snapshot,
        desk_overview=overview,
    )

    assert overview.nearest_call is not None
    assert f'href="#{overview.nearest_call.anchor_id}"' in rendered
    assert "Live options" in rendered
    assert "Point-in-time sensitivity" in rendered
    assert "AVG PREMIUM PACE / DAY" in rendered
    assert "weighted days" in rendered
    assert "DIVIDEND OVERLAP" not in rendered
    assert rendered.index("NIBWICK NOTES") < rendered.index("AVG PREMIUM PACE / DAY")


def test_open_call_workspace_keeps_exact_dte_in_expanded_contract_context() -> None:
    snapshot = DemoDashboardReader().execute()
    open_book = build_open_book(snapshot)
    roll_board = build_roll_board(snapshot)

    rendered = templates.env.get_template("workspaces/_open_book.html").render(
        snapshot=snapshot,
        open_book=open_book,
        roll_board=roll_board,
    )

    assert rendered.count('class="open-call-group"') == len(open_book.groups)
    assert rendered.count('class="roll-board-position-head"') == len(roll_board.rows)
    assert rendered.count('class="roll-board-contract"') == len(roll_board.rows)
    assert rendered.count('class="roll-board-clock"') == len(roll_board.rows)
    assert rendered.count('class="roll-board-urgency"') == len(roll_board.rows)
    assert rendered.count('class="roll-board-distance ') == len(roll_board.rows)
    assert rendered.count('class="roll-board-notional"') == len(roll_board.rows)
    assert rendered.count("data-open-book-section=") == 4
    assert "RISK LENS" in rendered
    assert "Carry, exposure, and IV pressure" in rendered
    assert "NET STOCK EXPOSURE" in rendered
    assert "IV COST IN THETA DAYS" in rendered
    assert "DELTA &middot; NEXT $1" in rendered
    assert "5D STOCK" in rendered
    assert "MOVE RISK" in rendered
    assert "IV +1" in rendered
    assert "MODEL INPUTS" in rendered
    assert 'data-open-book-section="roll-board" open' in rendered
    assert (
        '<details class="workspace-panel obligation-calendar open-book-section" '
        'data-open-book-section="calendar" open>'
    ) in rendered
    assert (
        '<details class="workspace-panel open-book-section" data-open-book-section="contracts">'
    ) in rendered
    assert rendered.count('class="open-book-section-control"') == 3
    assert "POSITIONS" in rendered
    assert "CURRENT MODEL THETA / DAY" in rendered
    assert "later expiries" in rendered
    assert "CALENDAR CLOCK" in rendered
    assert "OPTION VALUE / PREMIUM" in rendered
    for row in roll_board.rows:
        assert f'id="{row.anchor_id}"' in rendered
        if row.candidates:
            assert f"returnAnchor={row.anchor_id}" in rendered
        else:
            assert "REFRESH THE FULL CHAIN" in rendered
            assert f"returnAnchor={row.anchor_id}" in rendered
    assert "OBSERVED POSITION / NOT EVALUATED" not in rendered.upper()
    for row in open_book.rows:
        assert rendered.count(f"{row.days_to_expiration} DTE") >= 2


def _prior_session_underlying(stats) -> LiveUnderlyingPosition:
    return LiveUnderlyingPosition(
        symbol=stats.symbol,
        description=stats.company_name,
        shares=stats.shares,
        average_price=stats.average_cost,
        current_price=stats.current_price,
        market_value=stats.market_value,
        day_profit_loss=Decimal("0"),
        contract_capacity=stats.contract_capacity,
        open_call_contracts=stats.active_contracts,
        covered_contracts=stats.active_contracts,
        uncovered_contracts=0,
        coverage_percent=stats.coverage_percent,
        open_mark_profit_loss=Decimal("0"),
        calls=(),
        previous_close=stats.current_price,
        current_session_change_percent=Decimal("0"),
        quote_observed_at=datetime(2026, 8, 14, 20, 0, tzinfo=UTC),
        quote_quality="complete",
        quote_session=QuoteSession.PRIOR_SESSION,
        quote_evaluated_at=datetime(2026, 8, 17, 13, 40, tzinfo=UTC),
    )


def _snapshot_with_prior_session_tape():
    """A demo book re-stamped as Friday tape read on Monday morning."""

    snapshot = DemoDashboardReader().execute()
    underlyings = tuple(_prior_session_underlying(item) for item in snapshot.underlyings)
    return replace(
        snapshot,
        mode="live",
        live_position_book=LivePositionBook(
            underlyings=underlyings,
            calls=(),
            total_shares=sum(item.shares for item in underlyings),
            contract_capacity=sum(item.contract_capacity for item in underlyings),
            open_call_positions=0,
            open_call_contracts=0,
            covered_contracts=0,
            uncovered_contracts=0,
            coverage_percent=Decimal("0"),
            open_mark_profit_loss=Decimal("0"),
        ),
    )


def test_prior_session_tape_never_renders_a_name_row_captioned_day() -> None:
    snapshot = _snapshot_with_prior_session_tape()

    rendered = templates.env.get_template("partials/_underlyings.html").render(
        snapshot=snapshot,
        desk_overview=build_desk_overview(snapshot),
    )

    assert "<small>FRI CLOSE</small>" in rendered
    assert "<small>DAY</small>" not in rendered
    assert rendered.count("PRIOR SESSION · FRI 4:00 PM ET") == len(snapshot.underlyings)


def test_demo_book_keeps_the_day_caption_and_invents_no_quote_clock() -> None:
    snapshot = DemoDashboardReader().execute()

    rendered = templates.env.get_template("partials/_underlyings.html").render(
        snapshot=snapshot,
        desk_overview=build_desk_overview(snapshot),
    )

    assert "<small>DAY</small>" in rendered
    assert "PRIOR SESSION" not in rendered
    assert "position-quote-stamp" not in rendered


def test_header_flags_prior_session_names_outside_the_elements_the_poller_rewrites() -> None:
    snapshot = _snapshot_with_prior_session_tape()

    rendered = templates.env.get_template("partials/_sync_state.html").render(
        snapshot=snapshot,
        active_source_label="Schwab",
        sync_runtime={"interval_seconds": 900},
    )
    lag_note = rendered[rendered.index("data-quote-lag") :]

    assert "ON PRIOR-SESSION TAPE" in lag_note
    assert "data-sync-state" not in lag_note
    assert "data-sync-detail" not in lag_note


def test_header_stays_quiet_when_every_name_is_on_current_session_tape() -> None:
    rendered = templates.env.get_template("partials/_sync_state.html").render(
        snapshot=DemoDashboardReader().execute(),
        active_source_label="Demo",
        sync_runtime={"interval_seconds": 900},
    )

    assert "data-quote-lag" not in rendered


def test_short_put_row_pairs_received_premium_with_estimated_buyback_cost() -> None:
    snapshot = DemoDashboardReader().execute()
    put = PositionSummary(
        account_mask="...1234",
        symbol="URNM  260918P00050000",
        description="URNM SEP 18 2026 50 Put",
        asset_type="OPTION",
        quantity=Decimal("-1"),
        average_price=Decimal("1.20"),
        mark=Decimal("1.70"),
        market_value=Decimal("-170"),
        day_profit_loss=Decimal("-20"),
        day_profit_loss_percent=None,
        strategy="Short put",
        underlying_symbol="URNM",
        option_type="PUT",
        expiration_date=date(2026, 9, 18),
        strike=Decimal("50"),
        open_profit_loss=Decimal("-50"),
    )
    live_book = build_live_position_book(
        (*snapshot.positions, put),
        as_of=snapshot.as_of.date(),
    )
    updated = replace(snapshot, live_position_book=live_book)
    rendered = templates.env.get_template("workspaces/_open_book.html").render(
        snapshot=updated,
        open_book=build_open_book(updated),
        roll_board=build_roll_board(updated),
    )

    assert "IF ASSIGNED" not in rendered
    assert '<details class="open-option-row open-put-row' in rendered
    assert "URNM CASH-SECURED PUT" in rendered
    assert "PREMIUM / BUYBACK" in rendered
    assert "+$120.00" in rendered
    assert '<i class="negative">&minus;' in rendered
    assert "$170.00" in rendered
    assert "Received / mark estimate" in rendered
    assert "OPTION VALUE / PREMIUM" in rendered
    assert "EFFECTIVE ENTRY" in rendered
    assert "OPENING DATE UNAVAILABLE" in rendered
    assert "TERM NOT GUESSED" in rendered
    assert "MODEL INPUTS" in rendered
