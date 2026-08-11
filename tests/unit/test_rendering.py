from dataclasses import replace
from decimal import Decimal

from schwab_dashboard.application.dashboard.overview import build_desk_overview
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


def test_chart_events_render_as_accessible_buttons_with_one_popover_per_name() -> None:
    snapshot = DemoDashboardReader().execute()

    rendered = templates.env.get_template("partials/_underlyings.html").render(
        snapshot=snapshot,
        desk_overview=build_desk_overview(snapshot),
    )

    assert rendered.count("data-chart-event-popover") == len(snapshot.underlyings)
    assert rendered.count("data-chart-event-trigger") == sum(
        len(item.price_events) + len(item.share_trade_events) for item in snapshot.underlyings
    )
    assert 'aria-haspopup="dialog"' in rendered
    assert "data-linked-resolution-sequence" in rendered
    assert "data-chart-ledger-event" in rendered
