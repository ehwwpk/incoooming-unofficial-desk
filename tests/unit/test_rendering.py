import re
from dataclasses import asdict, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from fastapi.encoders import jsonable_encoder

from schwab_dashboard.application.dashboard.live_positions import build_live_position_book
from schwab_dashboard.application.dashboard.models import (
    LiveOpenOptionPosition,
    LivePositionBook,
    LiveUnderlyingPosition,
    PositionSummary,
)
from schwab_dashboard.application.dashboard.overview import (
    build_desk_overview,
    open_contract_side_copy,
)
from schwab_dashboard.application.expiration import ExpirationExpectation
from schwab_dashboard.application.market_time import QuoteSession
from schwab_dashboard.application.performance.projection import build_performance_comparison
from schwab_dashboard.application.risk.price_time import build_price_time_read
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
    assert pnl_class("not-a-number") == "muted"


def test_settlement_row_is_provisional_and_never_offers_a_dead_trade_action() -> None:
    assessment = SimpleNamespace(
        expectation=ExpirationExpectation.EXPECTED_ASSIGNMENT,
        expectation_label="EXPECTED ASSIGNMENT",
        reference_price=Decimal("206.25"),
        reference_label="EXPIRATION-DAY CLOSE",
        distance_per_share=Decimal("1.25"),
        assignment_shares=100,
        assignment_notional=Decimal("20500"),
    )
    rendered = templates.env.from_string(
        """{% from 'partials/_settlement_item.html' import settlement_item %}
        {{ settlement_item('call', 'abc', 'CVX', 1, 205, expires_on,
        'TRADING CLOSED · WAITING ON SCHWAB', assessment, 1, 99) }}"""
    ).render(expires_on=date(2026, 8, 21), assessment=assessment)

    assert "SHARE SALE EXPECTED" in rendered
    assert "Not booked until Schwab confirms it" in rendered
    assert "TRADING CLOSED · WAITING ON SCHWAB" in rendered
    assert "ROLL" not in rendered
    assert "CLOSE POSITION" not in rendered


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
    assert "TIME VALUE NOW" in rendered
    assert "PREMIUM RECEIVED" in rendered
    assert "OPTION VALUE NOW" in rendered
    assert "call-context-strip" in rendered
    assert rendered.count('role="button"') >= expected_option_cards
    for item in snapshot.underlyings:
        for call in item.open_call_clocks:
            assert f'data-option-campaign="{call.campaign_id}"' in rendered
    assert overview.nearest_call is not None
    assert f'id="{overview.nearest_call.anchor_id}"' in rendered
    assert "FIRST 3 BY EXPIRATION" not in rendered
    assert "BY EXPIRATION" in rendered
    assert "option status" in rendered
    assert "open short options, holding other inputs constant" in rendered


def test_option_card_pressure_read_sits_on_one_bottom_row() -> None:
    from dataclasses import replace

    snapshot = DemoDashboardReader().execute()
    item = snapshot.underlyings[0]
    call = item.open_call_clocks[0]
    price_time = build_price_time_read(
        position_delta=Decimal("-25"),
        position_gamma=Decimal("-4"),
        theta_per_day=Decimal("10"),
        current_underlying_price=Decimal("101"),
        previous_close=Decimal("100"),
        weekly_reference_price=Decimal("95"),
    )
    rendered = templates.env.from_string(
        "{% from 'partials/_underlying_option_cards.html' import underlying_call_card %}"
        "{{ underlying_call_card(call, item, snapshot) }}"
    ).render(
        call=replace(call, price_time_read=price_time),
        item=item,
        snapshot=snapshot,
    )

    assert "option-pressure-row" in rendered
    assert "price-pressure-plain" not in rendered
    assert "5D STOCK" in rendered
    assert "delta-move-pair" in rendered
    assert "<small>Time decay if price and IV hold still</small>" not in rendered
    assert "DOWN" in rendered
    assert "option-pressure-line" in rendered
    assert "UP-MOVE" not in rendered
    assert "HEATING" not in rendered
    assert "LAST SESSION" in rendered
    pressure_start = rendered.index("option-pressure-row")
    assert "<footer" not in rendered[pressure_start : pressure_start + 400]
    assert rendered.index("call-context-strip") < rendered.index("option-pressure-row")
    strip_end = rendered.index("option-pressure-row")
    strip_chunk = rendered[rendered.rfind("call-context-strip", 0, strip_end) : strip_end]
    assert "price-pressure-line" not in strip_chunk
    assert "price-pressure-plain" not in strip_chunk


def test_desk_put_card_matches_call_clocks_and_refuses_cash_secured_copy() -> None:
    from schwab_dashboard.application.dashboard.open_put_clocks import build_open_put_clocks

    snapshot = DemoDashboardReader().execute()
    item = next(row for row in snapshot.underlyings if row.symbol == "KTOS")
    put = LiveOpenOptionPosition(
        account_mask="...1234",
        option_symbol="KTOS  260821P00060000",
        underlying_symbol="KTOS",
        contracts=1,
        expires_on=date(2026, 8, 21),
        days_to_expiration=11,
        strike=Decimal("60"),
        entry_credit_per_share=Decimal("1.50"),
        estimated_mark_per_share=Decimal("0.40"),
        market_value=Decimal("-40"),
        open_profit_loss=Decimal("110"),
        day_profit_loss=Decimal("10"),
        underlying_price=Decimal("68"),
        strike_distance_per_share=Decimal("8"),
        strike_distance_percent=Decimal("11.76"),
        theta_per_share=Decimal("-0.05"),
        option_type="PUT",
        opened_on=date(2026, 7, 10),
        original_days_to_expiration=42,
    )
    clock = build_open_put_clocks((put,))[0]
    rendered = templates.env.from_string(
        "{% from 'partials/_underlying_option_cards.html' import underlying_put_card %}"
        "{{ underlying_put_card(put, item, snapshot) }}"
    ).render(put=clock, item=item, snapshot=snapshot)

    assert "SHORT PUT" in rendered
    assert "CASH-SECURED PUT" not in rendered
    assert "EFF ENTRY $58.50/SH" in rendered
    assert "SOLD JUL 10" in rendered
    assert "TERM NOT GUESSED" not in rendered
    assert "CALENDAR TIME SINCE SALE" in rendered
    assert "OPTION VALUE / CREDIT" in rendered
    assert "TIME VALUE NOW" in rendered
    assert "$0 / OTM" in rendered
    assert 'data-option-side="put"' in rendered
    assert 'data-option-campaign=""' in rendered
    assert clock.decay_stage in rendered


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


def test_settlement_link_occupies_the_observed_income_cell_not_the_live_book() -> None:
    snapshot = DemoDashboardReader().execute()
    overview = replace(
        build_desk_overview(snapshot),
        pending_settlement_contracts=12,
        pending_last_mark_profit_loss=Decimal("216.87"),
    )
    rendered = templates.env.get_template("partials/_summary.html").render(
        snapshot=snapshot,
        desk_overview=overview,
    )

    observed = re.search(
        r'<footer class="income-observed-bar"[^>]*>(.*?)</footer>',
        rendered,
        flags=re.S,
    )
    live_panel = rendered.split('<article class="pulse-panel live-book-pulse">', 1)[1]

    assert observed is not None
    assert 'class="desk-settlement-strip"' in observed.group(1)
    assert "BROKER CONFIRMATION PENDING" in observed.group(1)
    assert f"{overview.pending_settlement_contracts} CONTRACTS" in observed.group(1)
    assert "12 CONTRACTS · TRADING CLOSED" not in observed.group(1)
    assert "<small>TRADING CLOSED" in observed.group(1)
    assert "last-mark P/L $216.87 is provisional" in observed.group(1)
    assert 'class="desk-settlement-strip"' not in live_panel


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
    assert "Carry / IV" in rendered
    assert "NET STOCK EXPOSURE" in rendered
    assert "IV COST IN THETA DAYS" in rendered
    assert "DELTA &middot; NEXT $1" in rendered
    assert "5D STOCK" in rendered
    assert "price-pressure-plain" in rendered
    assert "price-pressure-plain" in rendered
    assert any(
        phrase in rendered
        for phrase in ("pressure is heating", "pressure is cooling", "roughly flat")
    )
    assert "LAST SESSION" in rendered
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
    for group in open_book.groups:
        entry_credit = sum((row.entry_credit for row in group.rows), Decimal(0))
        current_liability = sum((row.current_liability for row in group.rows), Decimal(0))
        expected_capture = (
            (entry_credit - current_liability) / entry_credit * Decimal("100")
            if entry_credit
            else Decimal(0)
        )
        assert group.premium_capture_percent == expected_capture
        assert f"{percent(group.premium_capture_percent)} CAPTURED" in rendered
    for row in open_book.rows:
        assert f"{percent(row.credit_capture_percent)} CAPTURED" in rendered
    for row in open_book.put_rows:
        assert f"{percent(row.credit_capture_percent)} CAPTURED" in rendered
    assert "LOWEST CASH COST" not in rendered
    assert "LEAST EXTRA TIME" not in rendered
    assert "MOST STRIKE ROOM" not in rendered
    if any(choice.highlight for row in roll_board.rows for choice in row.candidates):
        assert "NEAREST CASH AND TIME" in rendered
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


def _heating_price_time_read():
    return build_price_time_read(
        position_delta=Decimal("-25"),
        position_gamma=Decimal("-4"),
        theta_per_day=Decimal("10"),
        current_underlying_price=Decimal("101"),
        previous_close=Decimal("100"),
        weekly_reference_price=Decimal("95"),
    )


def _render_pressure_read(**kwargs) -> str:
    names = ", ".join(f"{key}={key}" for key in kwargs)
    return templates.env.from_string(
        "{% from 'partials/_price_time_fact.html' import price_pressure_read %}"
        f"{{{{ price_pressure_read({names}) }}}}"
    ).render(**kwargs)


def test_compact_pressure_read_keeps_face_and_session_without_plain_english() -> None:
    price_time = _heating_price_time_read()
    compact = _render_pressure_read(price_time=price_time, show_session=True, show_plain=False)
    full = _render_pressure_read(price_time=price_time, show_session=True, show_plain=True)
    defaulted = _render_pressure_read(price_time=price_time)

    assert "price-pressure-line" in compact
    assert "5D STOCK" in compact
    assert "HEATING" not in compact
    assert "LAST SESSION" in compact
    assert "price-pressure-plain" not in compact
    assert "price-pressure-plain" in full
    assert "pressure is heating" in full
    assert "price-pressure-plain" in defaulted
    assert "LAST SESSION" not in defaulted


def test_live_book_and_name_strip_keep_compact_pressure() -> None:
    call = LiveOpenOptionPosition(
        account_mask="...1234",
        option_symbol="CVX   260918C00215000",
        underlying_symbol="CVX",
        contracts=1,
        expires_on=date(2026, 9, 18),
        days_to_expiration=42,
        strike=Decimal("215"),
        entry_credit_per_share=Decimal("2.00"),
        estimated_mark_per_share=Decimal("1.20"),
        market_value=Decimal("-120"),
        open_profit_loss=Decimal("80"),
        day_profit_loss=Decimal("12"),
        underlying_price=Decimal("101"),
        strike_distance_per_share=Decimal("114"),
        strike_distance_percent=Decimal("113"),
        delta=Decimal("0.25"),
        gamma=Decimal("0.04"),
        theta_per_share=Decimal("-0.10"),
        underlying_previous_close=Decimal("100"),
        underlying_week_reference_price=Decimal("95"),
    )
    name = LiveUnderlyingPosition(
        symbol="CVX",
        description="Chevron",
        shares=700,
        average_price=Decimal("155.40"),
        current_price=Decimal("101"),
        market_value=Decimal("70700"),
        day_profit_loss=Decimal("0"),
        contract_capacity=7,
        open_call_contracts=1,
        covered_contracts=1,
        uncovered_contracts=6,
        coverage_percent=Decimal("14.3"),
        open_mark_profit_loss=Decimal("80"),
        calls=(call,),
        estimated_theta_per_day=Decimal("10"),
    )
    live_html = templates.env.get_template("partials/_live_position_book.html").render(
        live_book=LivePositionBook(
            underlyings=(name,),
            calls=(call,),
            total_shares=700,
            contract_capacity=7,
            open_call_positions=1,
            open_call_contracts=1,
            covered_contracts=1,
            uncovered_contracts=6,
            coverage_percent=Decimal("14.3"),
            open_mark_profit_loss=Decimal("80"),
        )
    )
    snapshot = DemoDashboardReader().execute()
    names_html = templates.env.get_template("partials/_underlyings.html").render(
        snapshot=snapshot,
        desk_overview=build_desk_overview(snapshot),
    )

    assert "price-pressure-line" in live_html
    assert "5D STOCK" in live_html
    assert "HEATING" not in live_html
    assert "LAST SESSION" in live_html
    assert "price-pressure-plain" not in live_html
    for chunk in re.findall(
        r'class="name-price-time"[^>]*>(.*?)</div>',
        names_html,
        flags=re.S,
    ):
        assert "price-pressure-plain" not in chunk
        if "price-pressure-line" in chunk:
            assert "LAST SESSION" in chunk
    analytics = re.search(
        r'class="name-analytics">(.*?)</div>\s*<div class="underlying-decision-grid"',
        names_html,
        flags=re.S,
    )
    assert analytics is not None
    cells = re.findall(r"<div(?: class=\"([^\"]*)\")?", analytics.group(1))
    assert len(cells) == 7
    assert cells[:-1] == [""] * 6
    assert cells[-1] == "name-price-time"
    assert "OPTION VALUE NOW" in analytics.group(1)
    assert "DIVIDENDS / 4W" not in analytics.group(1)
    assert "data-name-dividend-label" not in analytics.group(1)
    assert "data-name-dividends" in names_html
    first_row = build_desk_overview(snapshot).position_rows[0]
    value_cell = re.search(
        r"<span>OPTION VALUE NOW(?:[^<]*)</span><b(?: class=\"muted\")?>([^<]*)</b></div>",
        analytics.group(1),
    )
    assert value_cell is not None
    assert value_cell.group(1) == money(first_row.open_option_value_now)
    assert "<small>" not in analytics.group(1).split("OPTION VALUE NOW", 1)[1].split("</div>", 1)[0]
    source = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "schwab_dashboard"
        / "web"
        / "templates"
        / "partials"
        / "_underlyings.html"
    ).read_text(encoding="utf-8")
    assert 'class="name-price-time-read"' in source
    assert "OPTION VALUE NOW" in source
    assert 'row.open_option_value_now is none %} class="muted"' in source
    assert "data-name-dividend-label" not in source


def test_stale_option_mark_names_prior_session_on_the_tape_title() -> None:
    snapshot = DemoDashboardReader().execute()
    overview = build_desk_overview(snapshot)
    row = overview.position_rows[0]
    clock = replace(
        row.underlying.open_call_clocks[0],
        quote_observed_at=datetime(2026, 8, 6, 20, tzinfo=UTC),
        quote_observed_on=date(2026, 8, 6),
    )
    stale = replace(
        row,
        underlying=replace(row.underlying, open_call_clocks=(clock,)),
        evaluated_at=datetime(2026, 8, 7, 20, tzinfo=UTC),
    )
    live = replace(
        stale,
        underlying=replace(
            stale.underlying,
            open_call_clocks=(
                replace(
                    clock,
                    quote_observed_at=datetime(2026, 8, 7, 20, tzinfo=UTC),
                    quote_observed_on=date(2026, 8, 7),
                ),
            ),
        ),
    )
    assert stale.open_option_mark_is_prior_session
    assert stale.open_option_mark_stamp is not None
    assert not live.open_option_mark_is_prior_session
    html = templates.env.get_template("partials/_underlyings.html").render(
        snapshot=snapshot,
        desk_overview=replace(overview, position_rows=(stale, *overview.position_rows[1:])),
    )
    prior_session = "OPTION VALUE NOW · PRIOR SESSION"
    assert prior_session in html or prior_session.replace(" · ", " &middot; ") in html


def test_period_script_survives_removed_dividend_tape_label() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "schwab_dashboard" / "web"
    script = (root / "static" / "periods.js").read_text(encoding="utf-8")
    page = (root / "templates" / "dashboard.html").read_text(encoding="utf-8")
    assert 'querySelector("[data-name-dividend-label]").textContent' not in script
    assert 'card.querySelector("[data-name-dividend-label]")' in script
    assert "if (dividendLabel)" in script
    assert 'querySelectorAll("[data-name-dividends]")' in script
    assert "periods.js') }}?v=21" in page


def test_desk_header_uses_day_pl_not_today_nl_change() -> None:
    page = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "schwab_dashboard"
        / "web"
        / "templates"
        / "dashboard.html"
    ).read_text(encoding="utf-8")

    assert "DAY P/L" in page
    assert "TODAY <b" not in page
    assert "flow-adjusted-note" not in page
    assert "DEPOSIT EXCLUDED" not in page


def test_live_position_card_open_contracts_are_calls_plus_puts() -> None:
    call = LiveOpenOptionPosition(
        account_mask="...1234",
        option_symbol="KTOS  260918C00075000",
        underlying_symbol="KTOS",
        contracts=9,
        expires_on=date(2026, 9, 18),
        days_to_expiration=42,
        strike=Decimal("75"),
        entry_credit_per_share=Decimal("2.00"),
        estimated_mark_per_share=Decimal("1.20"),
        market_value=Decimal("-1080"),
        open_profit_loss=Decimal("720"),
        day_profit_loss=Decimal("12"),
        underlying_price=Decimal("60"),
        strike_distance_per_share=Decimal("15"),
        strike_distance_percent=Decimal("25"),
        delta=Decimal("0.25"),
        gamma=Decimal("0.04"),
        theta_per_share=Decimal("-0.10"),
        underlying_previous_close=Decimal("59"),
        underlying_week_reference_price=Decimal("55"),
        option_type="CALL",
    )
    put = LiveOpenOptionPosition(
        account_mask="...1234",
        option_symbol="KTOS  260918P00050000",
        underlying_symbol="KTOS",
        contracts=2,
        expires_on=date(2026, 9, 18),
        days_to_expiration=42,
        strike=Decimal("50"),
        entry_credit_per_share=Decimal("1.20"),
        estimated_mark_per_share=Decimal("1.70"),
        market_value=Decimal("-340"),
        open_profit_loss=Decimal("-100"),
        day_profit_loss=Decimal("-40"),
        underlying_price=Decimal("60"),
        strike_distance_per_share=Decimal("10"),
        strike_distance_percent=Decimal("16.67"),
        option_type="PUT",
    )
    name = LiveUnderlyingPosition(
        symbol="KTOS",
        description="Kratos Defense",
        shares=1000,
        average_price=Decimal("31.75"),
        current_price=Decimal("60"),
        market_value=Decimal("60000"),
        day_profit_loss=Decimal("0"),
        contract_capacity=10,
        open_call_contracts=9,
        covered_contracts=9,
        uncovered_contracts=1,
        coverage_percent=Decimal("90"),
        open_mark_profit_loss=Decimal("720"),
        calls=(call,),
        puts=(put,),
        estimated_theta_per_day=Decimal("10"),
    )
    rendered = templates.env.get_template("partials/_live_position_book.html").render(
        live_book=LivePositionBook(
            underlyings=(name,),
            calls=(call,),
            puts=(put,),
            total_shares=1000,
            contract_capacity=10,
            open_call_positions=1,
            open_call_contracts=9,
            covered_contracts=9,
            uncovered_contracts=1,
            coverage_percent=Decimal("90"),
            open_mark_profit_loss=Decimal("720"),
            open_put_positions=1,
            open_put_contracts=2,
        )
    )
    contracts = rendered.split("<span>OPEN CONTRACTS</span>", 1)[1].split("</div>", 1)[0]

    assert "<b>11</b>" in contracts
    assert "9 calls · 2 puts" in contracts
    assert "covered" not in contracts
    assert "10 lots · 90.0% covered by short calls" in rendered
    assert "OPEN OPTIONS" not in rendered


def test_open_contract_side_copy_omits_a_zero_side() -> None:
    assert open_contract_side_copy(0, 0) == "0 calls"
    assert open_contract_side_copy(1, 0) == "1 call"
    assert open_contract_side_copy(6, 0) == "6 calls"
    assert open_contract_side_copy(0, 1) == "1 put"
    assert open_contract_side_copy(0, 2) == "2 puts"
    assert open_contract_side_copy(1, 1) == "1 call · 1 put"
    assert open_contract_side_copy(9, 2) == "9 calls · 2 puts"


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


def test_open_contracts_are_calls_plus_puts_not_broker_lines() -> None:
    snapshot = DemoDashboardReader().execute()
    ktos = next(item for item in snapshot.underlyings if item.symbol == "KTOS")
    put = PositionSummary(
        account_mask="...1234",
        symbol="KTOS  260918P00050000",
        description="KTOS SEP 18 2026 50 Put",
        asset_type="OPTION",
        quantity=Decimal("-2"),
        average_price=Decimal("1.20"),
        mark=Decimal("1.70"),
        market_value=Decimal("-340"),
        day_profit_loss=Decimal("-40"),
        day_profit_loss_percent=None,
        strategy="Short put",
        underlying_symbol="KTOS",
        option_type="PUT",
        expiration_date=date(2026, 9, 18),
        strike=Decimal("50"),
        open_profit_loss=Decimal("-100"),
    )
    snapshot_with_put = replace(
        snapshot,
        live_position_book=build_live_position_book(
            (*snapshot.positions, put),
            as_of=snapshot.as_of.date(),
        ),
    )
    overview = build_desk_overview(snapshot_with_put)
    names = templates.env.get_template("partials/_underlyings.html").render(
        snapshot=snapshot_with_put,
        desk_overview=overview,
    )
    pulse = templates.env.get_template("partials/_summary.html").render(
        snapshot=snapshot_with_put,
        desk_overview=overview,
    )
    ktos_card = names.split('id="ktos-workspace"', 1)[1].split("</details>", 1)[0]
    ktos_contracts = ktos_card.split('class="position-contracts">', 1)[1].split("</div>", 1)[0]
    line_count = next(
        row.open_positions for row in overview.position_rows if row.underlying.symbol == "KTOS"
    )

    assert ktos.active_contracts == 8
    assert overview.open_put_contracts == 2
    assert overview.open_contracts == overview.open_call_contracts + 2
    assert sum(row.open_contracts for row in overview.position_rows) == overview.open_contracts
    ktos_row = next(row for row in overview.position_rows if row.underlying.symbol == "KTOS")
    assert ktos_row.open_call_contracts == 8
    assert ktos_row.open_put_contracts == 2
    assert ktos_row.open_contracts == 10
    assert line_count == 3
    assert f"<b>{overview.open_contracts}</b> TRADABLE CONTRACTS" in names
    assert f"<b>{overview.open_call_contracts}</b> CALLS · <b>2</b> PUTS" in names
    assert "OPTION POSITIONS" not in names
    assert "OPEN POSITIONS" not in ktos_contracts
    contract_count = f"<span>TRADABLE CONTRACTS</span><strong>{ktos_row.open_contracts}</strong>"
    assert contract_count in ktos_contracts
    assert "8 calls · 2 puts" in ktos_contracts
    assert f"<strong>{line_count}</strong>" not in ktos_contracts
    assert "covered" not in ktos_contracts
    assert "lots · " in ktos_card and "committed" in ktos_card
    assert "<span>Open calls</span><b>8</b>" in ktos_card
    assert "CASH-SECURED PUT" not in ktos_card
    assert "SHORT PUT" in ktos_card
    assert "EFF ENTRY $48.80/SH" in ktos_card
    assert "CALENDAR TIME SINCE SALE" in ktos_card
    assert "TERM NOT GUESSED" in ktos_card
    assert "OPTION VALUE / CREDIT" in ktos_card
    assert "NEAREST 3 BY EXPIRATION" not in ktos_card
    assert ">BY EXPIRATION<" in ktos_card
    assert "open short options" in ktos_card
    assert "AVG OPEN CALL IV <i>" in ktos_card
    assert "AVG OPEN IV <i>" not in ktos_card
    assert "Not cash." in ktos_card
    assert "OPEN OPTION POSITIONS" not in pulse
    assert "distinct strikes" not in pulse
    pulse_contracts = (
        f"<span>TRADABLE CONTRACTS</span>\n        <strong>{overview.open_contracts}</strong>"
    )
    assert pulse_contracts in pulse
    assert f"{overview.open_call_contracts} calls · 2 puts" in pulse


def test_demo_name_row_open_contracts_match_call_lots_not_strikes() -> None:
    snapshot = DemoDashboardReader().execute()
    overview = build_desk_overview(snapshot)
    rendered = templates.env.get_template("partials/_underlyings.html").render(
        snapshot=snapshot,
        desk_overview=overview,
    )
    pulse = templates.env.get_template("partials/_summary.html").render(
        snapshot=snapshot,
        desk_overview=overview,
    )
    cvx_card = rendered.split('id="cvx-workspace"', 1)[1].split("</details>", 1)[0]
    cvx_contracts = cvx_card.split('class="position-contracts">', 1)[1].split("</div>", 1)[0]
    cvx = next(item for item in snapshot.underlyings if item.symbol == "CVX")

    assert overview.open_positions == 6
    assert overview.open_contracts == 18
    assert cvx.active_contracts == 6
    assert "<b>18</b> TRADABLE CONTRACTS" in rendered
    assert "<b>18</b> CALLS" in rendered
    assert "OPTION POSITIONS" not in rendered
    assert "<span>TRADABLE CONTRACTS</span><strong>6</strong>" in cvx_contracts
    assert "6 calls" in cvx_contracts
    assert "<strong>3</strong>" not in cvx_contracts
    assert "OPEN OPTION POSITIONS" not in pulse
    assert "<strong>18</strong>" in pulse
    assert "18 calls" in pulse


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


def test_results_spine_keeps_series_key_beside_chart_and_economics_below_it() -> None:
    snapshot = DemoDashboardReader().execute()
    comparison = _results_comparison()
    comparison = replace(
        comparison,
        spine=replace(
            comparison.spine,
            risk=replace(
                comparison.spine.risk,
                status="early_sample",
                observations=9,
                annualized_volatility_percent=Decimal("33.98"),
            ),
        ),
    )
    rendered = templates.env.get_template("workspaces/_strategy_review.html").render(
        snapshot=replace(snapshot, performance_comparison=comparison),
        performance_comparison_payload=jsonable_encoder(asdict(comparison)),
    )

    assert "<h2>Benchmark</h2>" in rendered
    assert "Performance spine" not in rendered
    assert "Benchmark comparison" not in rendered
    assert "NORMALIZED RETURN PATH" not in rendered
    assert "FIRST OBSERVED VALUE = 0.00%" not in rendered
    assert "data-performance-sample" not in rendered
    assert "performance-compare-tape" not in rendered
    assert "performance-metric-rail" in rendered
    assert "data-performance-compare-canvas" in rendered
    assert "data-performance-compare-svg" not in rendered
    assert "<h3>Drawdown</h3>" in rendered
    assert "EARLY SAMPLE &middot; 9 SESSIONS" in rendered
    assert "EARLY ESTIMATE &middot; 9 SESSIONS" in rendered
    assert "33.98%" in rendered
    assert "performance-risk-withheld" not in rendered
    assert "needs 252" not in rendered
    assert "Observed peak to trough" in rendered
    assert rendered.count("data-results-window-math") == 1
    assert rendered.count("data-monthly-performance") == 1
    assert rendered.count("data-campaigns-drawer") == 1
    assert "<h3>Net liquidity</h3>" in rendered
    assert "RISK TAPE" not in rendered
    assert "CAPITAL USE" not in rendered
    assert "Drawdown, Volume, and Worst Day" not in rendered
    assert "Drawdown, vol, and worst day" not in rendered
    assert "Net Liquidity, Maintenance, and Buying Power" not in rendered
    assert "Net liq, maintenance, buying power" not in rendered
    assert "Credits, buybacks, live marks" in rendered
    assert ">MANAGED</span>" in rendered
    assert ">STARTING SHARES</span>" in rendered
    assert ">MANAGEMENT DIFFERENCE</span>" in rendered
    assert ">SPY</span>" in rendered
    assert "SPY &times; EXPOSURE" in rendered
    assert "cash flows removed" in rendered
    assert "share trades, no options" in rendered
    assert "MANAGED BOOK" not in rendered
    assert "SAME STARTING SHARES" not in rendered
    assert "Put to" in rendered
    assert "Called away" in rendered
    assert "What the return path demanded" not in rendered
    assert "What the cash leaned on" not in rendered
    assert "INCOOOMING-PERFORMANCE-V2" not in rendered
    assert "ALL FIGURES READ" not in rendered
    assert "Comparable or it stays blank" not in rendered
    assert "benchmark-policy-card" not in rendered
    assert "PRIMARY COUNTERFACTUAL" in rendered
    assert "<span>SLIPPAGE</span>" not in rendered
    assert "ASSIGNMENT LEDGER" not in rendered
    benchmark_heading = rendered.index("<h2>Benchmark</h2>")
    chart_stage_start = rendered.index('class="performance-compare-stage"')
    chart_stage_end = rendered.index("performance-economics-strip")
    chart_key = rendered.index("performance-metric-rail")
    assert benchmark_heading < chart_stage_start < chart_key
    assert rendered.index("performance-compare-chart") < chart_key < chart_stage_end
    assert chart_key < rendered.index("performance-management-card")
    assert chart_stage_end < rendered.index("data-performance-comparison-payload")


def test_results_spine_shows_assignment_ledger_only_when_shares_moved() -> None:
    snapshot = DemoDashboardReader().execute()
    comparison = _results_comparison()
    assigned = replace(
        comparison,
        spine=replace(
            comparison.spine,
            assignment_impact=replace(
                comparison.spine.assignment_impact,
                status="ready",
                assigned_call_contracts=2,
                called_away_shares=200,
            ),
        ),
    )
    rendered = templates.env.get_template("workspaces/_strategy_review.html").render(
        snapshot=replace(snapshot, performance_comparison=assigned),
        performance_comparison_payload=jsonable_encoder(asdict(assigned)),
    )

    assert "ASSIGNMENT LEDGER" in rendered
    assert "Calls and puts assigned" in rendered
    assert "200 shares called away" in rendered


def _results_comparison():
    return build_performance_comparison(
        balance_history=(
            {
                "account_mask": "...1234",
                "observed_at": datetime(2026, 8, 11, 20, tzinfo=UTC),
                "liquidation_value": Decimal("100000"),
                "initial_liquidation_value": Decimal("100000"),
            },
            {
                "account_mask": "...1234",
                "observed_at": datetime(2026, 8, 12, 20, tzinfo=UTC),
                "liquidation_value": Decimal("126000"),
                "initial_liquidation_value": Decimal("100000"),
            },
        ),
        cash_movements=(
            {
                "occurred_at": datetime(2026, 8, 12, 18, tzinfo=UTC),
                "movement_type": "transfer",
                "amount": Decimal("25000"),
            },
        ),
        position_history=(
            {
                "sync_run_id": "run-1",
                "account_mask": "...1234",
                "observed_at": datetime(2026, 8, 11, 20, tzinfo=UTC),
                "symbol": "KTOS",
                "asset_type": "EQUITY",
                "net_quantity": Decimal("500"),
            },
        ),
        daily_bars=(
            {"symbol": "KTOS", "trade_date": date(2026, 8, 11), "close": Decimal("100")},
            {"symbol": "KTOS", "trade_date": date(2026, 8, 12), "close": Decimal("100")},
            {"symbol": "SPY", "trade_date": date(2026, 8, 11), "close": Decimal("100")},
            {"symbol": "SPY", "trade_date": date(2026, 8, 12), "close": Decimal("100")},
        ),
    )
