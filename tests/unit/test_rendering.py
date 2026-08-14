from dataclasses import replace
from decimal import Decimal

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
    assert rendered.count('role="group" aria-label="Market chart style"') == len(
        snapshot.underlyings
    )
    assert rendered.count('role="group" aria-label="Option campaign visibility"') == len(
        snapshot.underlyings
    )
    assert rendered.count('role="group" aria-label="Chart range"') == len(
        snapshot.underlyings
    )
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
    assert "All open short options" in rendered


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
    assert rendered.count("data-open-book-section=") == 3
    assert 'data-open-book-section="roll-board" open' in rendered
    assert (
        '<details class="workspace-panel obligation-calendar open-book-section" '
        'data-open-book-section="calendar" open>'
    ) in rendered
    assert (
        '<details class="workspace-panel open-book-section" data-open-book-section="contracts">'
    ) in rendered
    assert rendered.count('class="open-book-section-control"') == 3
    assert "CALENDAR CLOCK" in rendered
    assert "OPTION VALUE / PREMIUM" in rendered
    for row in roll_board.rows:
        assert f'id="{row.anchor_id}"' in rendered
        if row.candidates:
            assert f'returnAnchor={row.anchor_id}' in rendered
        else:
            assert "REFRESH THE FULL CHAIN" in rendered
            assert f'returnAnchor={row.anchor_id}' in rendered
    assert "OBSERVED POSITION / NOT EVALUATED" not in rendered.upper()
    for row in open_book.rows:
        assert rendered.count(f"{row.days_to_expiration} DTE") >= 2
