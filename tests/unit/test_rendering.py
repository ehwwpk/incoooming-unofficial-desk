from dataclasses import replace
from datetime import date
from decimal import Decimal

from schwab_dashboard.application.dashboard.live_positions import build_live_position_book
from schwab_dashboard.application.dashboard.models import PositionSummary
from schwab_dashboard.application.dashboard.overview import build_desk_overview
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
