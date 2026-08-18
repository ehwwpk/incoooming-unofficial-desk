import re
from dataclasses import asdict, replace
from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi.encoders import jsonable_encoder

from schwab_dashboard.application.dashboard.live_positions import build_live_position_book
from schwab_dashboard.application.dashboard.models import (
    LiveOpenOptionPosition,
    LivePositionBook,
    LiveUnderlyingPosition,
    PositionSummary,
)
from schwab_dashboard.application.dashboard.overview import build_desk_overview
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
    assert "<footer" not in rendered[rendered.index("option-pressure-row") : rendered.index("option-pressure-row") + 400]
    assert rendered.index("call-context-strip") < rendered.index("option-pressure-row")
    strip_end = rendered.index("option-pressure-row")
    strip_chunk = rendered[rendered.rfind("call-context-strip", 0, strip_end) : strip_end]
    assert "price-pressure-line" not in strip_chunk
    assert "price-pressure-plain" not in strip_chunk


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
    assert "price-pressure-plain" in rendered
    assert "price-pressure-plain" in rendered
    assert "pressure is heating" in rendered or "pressure is cooling" in rendered or "roughly flat" in rendered
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
    compact = _render_pressure_read(
        price_time=price_time, show_session=True, show_plain=False
    )
    full = _render_pressure_read(
        price_time=price_time, show_session=True, show_plain=True
    )
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


def test_results_spine_keeps_tape_above_the_chart_and_drops_workshop_copy() -> None:
    snapshot = DemoDashboardReader().execute()
    comparison = _results_comparison()
    rendered = templates.env.get_template("workspaces/_strategy_review.html").render(
        snapshot=replace(snapshot, performance_comparison=comparison),
        performance_comparison_payload=jsonable_encoder(asdict(comparison)),
    )

    assert "Did the premium work earn its keep?" in rendered
    assert "performance-compare-tape" in rendered
    assert "Drawdown, Volume, and Worst Day" in rendered
    assert "Net Liquidity, Maintenance, and Buying Power" in rendered
    assert "RISK TAPE" not in rendered
    assert "CAPITAL USE" not in rendered
    assert "Drawdown, vol, and worst day" not in rendered
    assert "Net liq, maintenance, buying power" not in rendered
    assert "Credits, buybacks, live marks" in rendered
    assert "What the return path demanded" not in rendered
    assert "What the cash leaned on" not in rendered
    assert "INCOOOMING-PERFORMANCE-V2" not in rendered
    assert "ALL FIGURES READ" not in rendered
    assert "Comparable or it stays blank" not in rendered
    assert "benchmark-policy-card" not in rendered
    assert "PRIMARY COUNTERFACTUAL" in rendered
    assert "<span>SLIPPAGE</span>" not in rendered
    assert "ASSIGNMENT LEDGER" not in rendered
    assert rendered.index("performance-compare-tape") < rendered.index(
        "performance-compare-chart"
    )
    assert rendered.index("performance-compare-chart") < rendered.index(
        "performance-coverage-rail"
    )


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
