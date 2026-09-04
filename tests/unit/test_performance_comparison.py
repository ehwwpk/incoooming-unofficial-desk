from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from schwab_dashboard.application.performance.projection import build_performance_comparison
from schwab_dashboard.application.performance.returns import build_time_weighted_returns

D = Decimal


def test_time_weighted_return_excludes_deposit_before_chaining() -> None:
    comparison = build_performance_comparison(
        balance_history=(
            _balance("2026-08-11T20:00:00+00:00", "100000", "99000"),
            _balance("2026-08-12T20:00:00+00:00", "126000", "100000"),
            _balance("2026-08-13T20:00:00+00:00", "127260", "126000"),
        ),
        cash_movements=(
            {
                "occurred_at": datetime(2026, 8, 12, 18, tzinfo=UTC),
                "movement_type": "transfer",
                "amount": D("25000"),
            },
        ),
    )

    assert comparison.external_flows_excluded == D("25000")
    assert [point.daily_return_percent for point in comparison.actual.points] == [
        None,
        D("1.00"),
        D("1.00"),
    ]
    assert comparison.actual.return_percent == D("2.0100")
    assert comparison.actual.points[1].return_quality == "estimated"
    assert comparison.spine.risk.observations == 1
    assert comparison.shares_without_options.status == "not_available"
    assert comparison.market_reference.return_percent is None


def test_owner_flow_already_inside_the_first_anchor_is_not_counted_as_excluded() -> None:
    comparison = build_performance_comparison(
        balance_history=(
            _balance("2026-08-11T20:00:00+00:00", "125000", "100000"),
            _balance("2026-08-12T20:00:00+00:00", "126250", "125000"),
        ),
        cash_movements=(
            {
                "occurred_at": datetime(2026, 8, 11, 18, tzinfo=UTC),
                "movement_type": "transfer",
                "amount": D("25000"),
            },
        ),
    )

    assert comparison.actual.points[0].external_flow == D("0")
    assert comparison.external_flows_excluded == D("0")
    assert comparison.actual.return_percent == D("1.00")


def test_owner_flow_is_unitized_across_complete_intraday_sync_cohorts() -> None:
    points = build_time_weighted_returns(
        balance_history=(
            _run_balance("close-1", "2026-08-11T20:00:00+00:00", "100"),
            _run_balance("before-flow", "2026-08-12T16:00:00+00:00", "110"),
            _run_balance("after-flow", "2026-08-12T18:01:00+00:00", "160"),
            _run_balance("close-2", "2026-08-12T20:00:00+00:00", "176"),
        ),
        cash_movements=(
            {
                "account_id": "account-a",
                "occurred_at": datetime(2026, 8, 12, 18, tzinfo=UTC),
                "movement_type": "transfer",
                "amount": D("50"),
            },
        ),
    )

    # 10% before funding, no change across the receipt, then 10% after it.
    # The old endpoint convention reported (176 - 100 - 50) / 100 = 26%.
    assert points[-1].daily_return_percent == D("21.00")
    assert points[-1].external_flow == D("50")
    assert points[-1].return_quality == "estimated"


def test_partial_intraday_account_cohort_is_not_used_for_unitization() -> None:
    points = build_time_weighted_returns(
        balance_history=(
            _run_balance("close-1", "2026-08-11T20:00:00+00:00", "100", "account-a"),
            _run_balance("close-1", "2026-08-11T20:00:00+00:00", "100", "account-b"),
            _run_balance("partial", "2026-08-12T18:01:00+00:00", "75", "account-a"),
            _run_balance("close-2", "2026-08-12T20:00:00+00:00", "130", "account-a"),
            _run_balance("close-2", "2026-08-12T20:00:00+00:00", "120", "account-b"),
        ),
        cash_movements=(
            {
                "account_id": "account-a",
                "occurred_at": datetime(2026, 8, 12, 18, tzinfo=UTC),
                "movement_type": "transfer",
                "amount": D("50"),
            },
        ),
    )

    assert points[-1].daily_return_percent == D("0")
    assert points[-1].return_quality == "estimated"


def test_unexplained_nonzero_cash_fails_the_return_link_closed() -> None:
    balances = (
        _run_balance("close-1", "2026-08-11T20:00:00+00:00", "100"),
        _run_balance("close-2", "2026-08-12T20:00:00+00:00", "110"),
        _run_balance("close-3", "2026-08-13T20:00:00+00:00", "111"),
    )
    cash = (
        {
            "account_id": "account-a",
            "occurred_at": datetime(2026, 8, 12, 18, tzinfo=UTC),
            "movement_type": "other",
            "amount": D("10"),
        },
    )
    points = build_time_weighted_returns(balance_history=balances, cash_movements=cash)

    assert points[1].daily_return_percent is None
    assert points[1].interval_return_percent is None
    assert points[1].quality == "unexplained_cash_movement"
    assert points[1].cumulative_return_percent is None
    assert points[2].daily_return_percent == D("100") / D("110")
    assert points[2].cumulative_return_percent is None

    comparison = build_performance_comparison(
        balance_history=balances,
        cash_movements=cash,
    )
    assert any(
        warning == "1 return link is withheld until unexplained cash is classified."
        for warning in comparison.warnings
    )


def test_zero_net_same_instant_other_cash_is_harmless() -> None:
    occurred_at = datetime(2026, 8, 12, 18, tzinfo=UTC)
    points = build_time_weighted_returns(
        balance_history=(
            _run_balance("close-1", "2026-08-11T20:00:00+00:00", "100"),
            _run_balance("close-2", "2026-08-12T20:00:00+00:00", "101"),
        ),
        cash_movements=(
            {
                "account_id": "account-a",
                "occurred_at": occurred_at,
                "movement_type": "other",
                "amount": D("10"),
            },
            {
                "account_id": "account-a",
                "occurred_at": occurred_at,
                "movement_type": "other",
                "amount": D("-10"),
            },
        ),
    )

    assert points[-1].daily_return_percent == D("1.00")
    assert points[-1].quality == "linked"


def test_internal_dividend_remains_in_investment_return() -> None:
    points = build_time_weighted_returns(
        balance_history=(
            _run_balance("close-1", "2026-08-11T20:00:00+00:00", "100"),
            _run_balance("close-2", "2026-08-12T20:00:00+00:00", "101"),
        ),
        cash_movements=(
            {
                "account_id": "account-a",
                "occurred_at": datetime(2026, 8, 12, 18, tzinfo=UTC),
                "movement_type": "dividend",
                "amount": D("1"),
            },
        ),
    )

    assert points[-1].daily_return_percent == D("1.00")
    assert points[-1].external_flow == D("0")


def test_recognized_fee_cash_remains_in_investment_return() -> None:
    points = build_time_weighted_returns(
        balance_history=(
            _run_balance("close-1", "2026-08-11T20:00:00+00:00", "100"),
            _run_balance("close-2", "2026-08-12T20:00:00+00:00", "99"),
        ),
        cash_movements=(
            {
                "account_id": "account-a",
                "occurred_at": datetime(2026, 8, 12, 18, tzinfo=UTC),
                "movement_type": "fee",
                "amount": D("-1"),
            },
        ),
    )

    assert points[-1].daily_return_percent == D("-1.00")
    assert points[-1].quality == "linked"


def test_utc_after_hours_snapshots_stay_on_the_same_market_day() -> None:
    comparison = build_performance_comparison(
        balance_history=(
            _balance("2026-08-14T20:00:00+00:00", "101000", "100000"),
            _balance("2026-08-15T02:00:00+00:00", "101000", "100000"),
        ),
        cash_movements=(),
    )

    assert len(comparison.actual.points) == 1
    assert comparison.actual.points[0].date.isoformat() == "2026-08-14"
    assert comparison.actual.return_percent is None


def test_return_chain_fails_closed_when_account_coverage_changes() -> None:
    first_account = _balance("2026-08-11T20:00:00+00:00", "50000", "50000")
    second_account = {
        **_balance("2026-08-11T20:00:00+00:00", "50000", "50000"),
        "account_mask": "...5678",
    }
    comparison = build_performance_comparison(
        balance_history=(
            first_account,
            second_account,
            _balance("2026-08-12T20:00:00+00:00", "51000", "50000"),
            _balance("2026-08-13T20:00:00+00:00", "52000", "51000"),
        ),
        cash_movements=(),
    )

    assert [point.quality for point in comparison.actual.points] == [
        "observed_anchor",
        "account_coverage_changed",
        "linked_after_incomplete_history",
    ]
    assert comparison.actual.points[-1].daily_return_percent == D("1000") / D("51000") * D("100")
    assert comparison.actual.points[-1].cumulative_return_percent is None
    assert comparison.actual.return_percent is None


def test_comparison_refuses_to_invent_missing_benchmarks() -> None:
    comparison = build_performance_comparison(balance_history=(), cash_movements=())

    assert comparison.actual.status == "waiting"
    assert comparison.actual.return_percent is None
    assert all(
        series.status == "not_available"
        for series in (
            comparison.shares_without_options,
            comparison.option_overlay,
            comparison.market_reference,
            comparison.levered_market_reference,
        )
    )


def test_comparison_derives_static_starting_shares_and_executed_overlay() -> None:
    comparison = build_performance_comparison(
        balance_history=(
            _balance("2026-08-11T20:00:00+00:00", "100000", "100000"),
            _balance("2026-08-12T20:00:00+00:00", "101000", "100000"),
        ),
        cash_movements=(),
        position_history=(
            {
                "sync_run_id": "run-1",
                "account_mask": "...1234",
                "observed_at": datetime(2026, 8, 11, 20, tzinfo=UTC),
                "symbol": "KTOS",
                "asset_type": "EQUITY",
                "net_quantity": D("100"),
            },
        ),
        daily_bars=(
            {"symbol": "KTOS", "trade_date": datetime(2026, 8, 11).date(), "close": D("60")},
            {"symbol": "KTOS", "trade_date": datetime(2026, 8, 12).date(), "close": D("63")},
        ),
        executions=(
            {
                "occurred_at": datetime(2026, 8, 12, 15, tzinfo=UTC),
                "asset_type": "option",
                "side": "sell",
                "position_effect": "opening",
                "net_cash": D("200"),
            },
        ),
    )

    assert comparison.shares_without_options.status == "derived"
    assert comparison.shares_without_options.return_percent == D("0.3")
    assert comparison.option_overlay.status == "cash_only"
    assert comparison.option_overlay.return_percent == D("0.2")


def test_share_baseline_freezes_inventory_nearest_to_return_window() -> None:
    comparison = build_performance_comparison(
        balance_history=(
            _balance("2026-08-11T20:00:00+00:00", "100000", "100000"),
            _balance("2026-08-12T20:00:00+00:00", "101000", "100000"),
        ),
        cash_movements=(),
        position_history=(
            {
                "sync_run_id": "old",
                "observed_at": datetime(2026, 7, 1, 20, tzinfo=UTC),
                "symbol": "KTOS",
                "asset_type": "EQUITY",
                "net_quantity": D("50"),
            },
            {
                "sync_run_id": "aligned",
                "observed_at": datetime(2026, 8, 11, 18, tzinfo=UTC),
                "symbol": "KTOS",
                "asset_type": "EQUITY",
                "net_quantity": D("100"),
            },
        ),
        daily_bars=(
            {"symbol": "KTOS", "trade_date": datetime(2026, 8, 11).date(), "close": D("60")},
            {"symbol": "KTOS", "trade_date": datetime(2026, 8, 12).date(), "close": D("63")},
        ),
    )

    assert comparison.shares_without_options.status == "derived"
    assert comparison.shares_without_options.return_percent == D("0.3")


def test_market_reference_rejects_materially_partial_history() -> None:
    comparison = build_performance_comparison(
        balance_history=(
            _balance("2026-08-01T20:00:00+00:00", "100000", "100000"),
            _balance("2026-08-12T20:00:00+00:00", "101000", "100000"),
        ),
        cash_movements=(),
        daily_bars=(
            {"symbol": "SPY", "trade_date": datetime(2026, 8, 10).date(), "close": D("640")},
            {"symbol": "SPY", "trade_date": datetime(2026, 8, 12).date(), "close": D("645")},
        ),
    )

    assert comparison.market_reference.status == "not_available"
    assert comparison.market_reference.return_percent is None


def test_market_reference_rejects_a_zero_price_placeholder() -> None:
    comparison = build_performance_comparison(
        balance_history=(
            _balance("2026-08-11T20:00:00+00:00", "100000", "100000"),
            _balance("2026-08-12T20:00:00+00:00", "101000", "100000"),
        ),
        cash_movements=(),
        daily_bars=(
            {"symbol": "SPY", "trade_date": date(2026, 8, 11), "close": D("640")},
            {"symbol": "SPY", "trade_date": date(2026, 8, 12), "close": D("0")},
        ),
    )

    assert comparison.market_reference.status == "not_available"
    assert comparison.market_reference.return_percent is None


def test_market_references_show_a_short_missing_close_as_an_estimated_carry() -> None:
    comparison = build_performance_comparison(
        balance_history=(
            _balance("2026-08-11T20:00:00+00:00", "100000", "100000"),
            _balance("2026-08-12T20:00:00+00:00", "100000", "100000"),
            _balance("2026-08-13T20:00:00+00:00", "101000", "100000"),
        ),
        cash_movements=(),
        position_history=(_lot("KTOS", "100", "2026-08-11T20:00:00+00:00"),),
        daily_bars=(
            *_bars(
                "KTOS",
                ("2026-08-11", "100"),
                ("2026-08-12", "100"),
                ("2026-08-13", "101"),
            ),
            *_bars("SPY", ("2026-08-11", "100"), ("2026-08-13", "102")),
        ),
        margin_interest_rate_percent=D("0"),
    )

    assert comparison.market_reference.status == "carried_forward"
    assert comparison.levered_market_reference.status == "carried_forward"
    assert [point.date for point in comparison.market_reference.points] == [
        date(2026, 8, 11),
        date(2026, 8, 12),
        date(2026, 8, 13),
    ]
    assert comparison.market_reference.points[1].value_quality == "estimated"
    assert comparison.levered_market_reference.points[1].value_quality == "estimated"
    assert comparison.matched.quality == "estimated"


def test_headline_difference_reads_both_series_on_their_last_common_session() -> None:
    comparison = build_performance_comparison(
        balance_history=(
            _balance("2026-08-12T20:00:00+00:00", "100000", "100000"),
            _balance("2026-08-13T20:00:00+00:00", "101000", "100000"),
            _balance("2026-08-14T20:00:00+00:00", "102010", "101000"),
            _balance("2026-08-17T20:00:00+00:00", "103030.10", "102010"),
        ),
        cash_movements=(),
        position_history=(_lot("KTOS", "100", "2026-08-12T20:00:00+00:00"),),
        daily_bars=(
            *_bars("KTOS", ("2026-08-12", "100"), ("2026-08-13", "101"), ("2026-08-14", "102")),
            *_bars("SPY", ("2026-08-12", "640"), ("2026-08-13", "640"), ("2026-08-14", "640")),
        ),
    )

    # The managed book is valued live through Monday; no daily close exists past
    # Friday, so Friday is the only honest place to read the difference.
    assert comparison.actual.points[-1].date == date(2026, 8, 17)
    assert comparison.matched.as_of == date(2026, 8, 14)
    assert comparison.matched.managed_return_percent == D("2.0100")
    assert comparison.matched.shares_return_percent == D("0.2")
    assert comparison.spine.management_edge.return_difference_percent == D("1.8100")
    assert comparison.matched.quality == "derived"
    assert comparison.spine.management_edge.status == "derived"
    assert "weakest required input (derived)" in comparison.matched.method_note
    assert comparison.actual.return_percent > comparison.matched.managed_return_percent


def test_frozen_baseline_holds_an_exited_symbol_flat_rather_than_dropping_sessions() -> None:
    comparison = build_performance_comparison(
        balance_history=(
            _balance("2026-08-12T20:00:00+00:00", "100000", "100000"),
            _balance("2026-08-13T20:00:00+00:00", "101000", "100000"),
            _balance("2026-08-14T20:00:00+00:00", "102010", "101000"),
        ),
        cash_movements=(),
        position_history=(
            _lot("KTOS", "100", "2026-08-12T20:00:00+00:00"),
            _lot("INTC", "100", "2026-08-12T20:00:00+00:00"),
        ),
        daily_bars=(
            *_bars("KTOS", ("2026-08-12", "100"), ("2026-08-13", "101"), ("2026-08-14", "102")),
            *_bars("INTC", ("2026-08-12", "20"), ("2026-08-13", "21")),
            *_bars("SPY", ("2026-08-12", "640"), ("2026-08-13", "640"), ("2026-08-14", "640")),
        ),
    )

    series = comparison.shares_without_options
    assert series.status == "carried_forward"
    assert series.points[-1].date == date(2026, 8, 14)
    assert series.return_percent == D("0.3")
    assert "INTC at its Aug 13 close" in series.method_note
    assert comparison.matched.quality == "estimated"
    assert comparison.spine.management_edge.status == "estimated"


def test_frozen_baseline_carries_past_a_zero_close_placeholder() -> None:
    comparison = build_performance_comparison(
        balance_history=(
            _balance("2026-08-11T20:00:00+00:00", "100000", "100000"),
            _balance("2026-08-12T20:00:00+00:00", "100000", "100000"),
            _balance("2026-08-13T20:00:00+00:00", "101000", "100000"),
        ),
        cash_movements=(),
        position_history=(_lot("KTOS", "100", "2026-08-11T20:00:00+00:00"),),
        daily_bars=(
            *_bars("KTOS", ("2026-08-11", "100"), ("2026-08-12", "0"), ("2026-08-13", "101")),
            *_bars("SPY", ("2026-08-11", "640"), ("2026-08-12", "640"), ("2026-08-13", "640")),
        ),
    )

    series = comparison.shares_without_options
    assert [point.value for point in series.points] == [D("100000"), D("100000"), D("100100")]
    assert series.points[1].value_quality == "estimated"
    assert series.status == "carried_forward"


def test_frozen_baseline_reports_no_carry_when_every_symbol_prices_each_session() -> None:
    comparison = build_performance_comparison(
        balance_history=(
            _balance("2026-08-12T20:00:00+00:00", "100000", "100000"),
            _balance("2026-08-13T20:00:00+00:00", "101000", "100000"),
        ),
        cash_movements=(),
        position_history=(
            _lot("KTOS", "100", "2026-08-12T20:00:00+00:00"),
            _lot("INTC", "100", "2026-08-12T20:00:00+00:00"),
        ),
        daily_bars=(
            # INTC has no bar before the window opens, so Aug 11 is unpriceable
            # rather than a session KTOS carried.
            *_bars("KTOS", ("2026-08-11", "99"), ("2026-08-12", "100"), ("2026-08-13", "101")),
            *_bars("INTC", ("2026-08-12", "20"), ("2026-08-13", "21")),
            *_bars("SPY", ("2026-08-12", "640"), ("2026-08-13", "640")),
        ),
    )

    series = comparison.shares_without_options
    assert series.status == "derived"
    assert "held flat" not in series.method_note
    assert [point.date.isoformat() for point in series.points] == ["2026-08-12", "2026-08-13"]


def test_weekend_broker_snapshots_do_not_chain_as_return_days() -> None:
    comparison = build_performance_comparison(
        balance_history=(
            _balance("2026-08-14T20:00:00+00:00", "100000", "100000"),
            _balance("2026-08-15T20:00:00+00:00", "100500", "100000"),
            _balance("2026-08-16T20:00:00+00:00", "100500", "100500"),
            _balance("2026-08-17T20:00:00+00:00", "101505", "100500"),
        ),
        cash_movements=(),
        daily_bars=_bars("SPY", ("2026-08-13", "640"), ("2026-08-14", "640")),
    )

    assert [point.date.isoformat() for point in comparison.actual.points] == [
        "2026-08-14",
        "2026-08-17",
    ]
    # Saturday and Sunday are not return days, but the drift the broker booked
    # across them is still the owner's money. It belongs to Monday's session
    # rather than being dropped on the floor.
    assert comparison.actual.return_percent == D("1.50500")


def test_chain_keeps_value_that_accrues_between_the_last_sync_and_the_next_open() -> None:
    comparison = build_performance_comparison(
        # The broker reports Wednesday opening at 101,000 even though the last
        # Tuesday snapshot closed at 100,000. Measuring Wednesday from the
        # broker's opening would discard that 1,000 entirely.
        balance_history=(
            _balance("2026-08-11T20:00:00+00:00", "100000", "100000"),
            _balance("2026-08-12T20:00:00+00:00", "102010", "101000"),
        ),
        cash_movements=(),
        daily_bars=_bars("SPY", ("2026-08-11", "640"), ("2026-08-12", "640")),
    )

    assert comparison.actual.return_percent == D("2.010")
    assert comparison.actual.points[-1].quality == "linked"


def test_a_weekend_transfer_is_still_excluded_from_the_next_session() -> None:
    comparison = build_performance_comparison(
        balance_history=(
            _balance("2026-08-14T20:00:00+00:00", "100000", "100000"),
            _balance("2026-08-17T20:00:00+00:00", "126000", "100000"),
        ),
        cash_movements=(
            # Settles Saturday, which is never its own return day. It must
            # still be attributed to Monday or the deposit reads as a 26% gain.
            {
                "occurred_at": datetime(2026, 8, 15, 14, tzinfo=UTC),
                "movement_type": "transfer",
                "amount": D("25000"),
            },
        ),
        daily_bars=_bars("SPY", ("2026-08-13", "640"), ("2026-08-14", "640")),
    )

    assert comparison.external_flows_excluded == D("25000")
    assert comparison.actual.return_percent == D("1.00")


def test_unlevered_spy_stays_a_price_line_and_ignores_account_leverage() -> None:
    comparison = build_performance_comparison(
        balance_history=(
            _balance("2026-08-11T20:00:00+00:00", "50000", "50000"),
            _balance("2026-08-12T20:00:00+00:00", "52000", "50000"),
        ),
        cash_movements=(),
        position_history=(_lot("KTOS", "100", "2026-08-11T20:00:00+00:00"),),
        daily_bars=(
            *_bars("KTOS", ("2026-08-11", "100"), ("2026-08-12", "104")),
            *_bars("SPY", ("2026-08-11", "640"), ("2026-08-12", "646.40")),
        ),
    )

    assert comparison.market_reference.status == "price_only"
    assert comparison.market_reference.return_percent == D("1.00")
    assert comparison.matched.market_return_percent == D("1.00")


def test_levered_spy_buys_the_starting_exposure_once_and_lets_leverage_drift() -> None:
    comparison = build_performance_comparison(
        balance_history=(
            _balance("2026-08-11T20:00:00+00:00", "50000", "50000"),
            _balance("2026-08-12T20:00:00+00:00", "52000", "50000"),
        ),
        cash_movements=(),
        position_history=(_lot("KTOS", "500", "2026-08-11T20:00:00+00:00"),),
        daily_bars=(
            *_bars("KTOS", ("2026-08-11", "100"), ("2026-08-12", "104")),
            *_bars("SPY", ("2026-08-11", "100"), ("2026-08-12", "101")),
        ),
        margin_interest_rate_percent=D("0"),
    )

    series = comparison.levered_market_reference
    assert series.status == "derived_levered"
    # 50,000 of KTOS bought as 500 SPY shares, financed with a 0 cash residual
    # here because exposure equals net liquidation. A later buy in the real
    # book must not mint extra SPY — that would be daily rematch cosplay.
    assert series.points[0].value == D("50000")
    assert series.return_percent == D("1.00")
    assert "rather than being reset daily" in series.method_note


def test_levered_spy_charges_margin_interest_on_the_borrowed_cash() -> None:
    comparison = build_performance_comparison(
        balance_history=(
            _balance("2026-08-11T20:00:00+00:00", "50000", "50000"),
            _balance("2026-08-12T20:00:00+00:00", "52000", "50000"),
        ),
        cash_movements=(),
        position_history=(_lot("KTOS", "1000", "2026-08-11T20:00:00+00:00"),),
        daily_bars=(
            *_bars("KTOS", ("2026-08-11", "100"), ("2026-08-12", "100")),
            *_bars("SPY", ("2026-08-11", "100"), ("2026-08-12", "100")),
        ),
        margin_interest_rate_percent=D("36"),
    )

    # 100,000 of SPY on 50,000 equity leaves a 50,000 debit. One calendar day
    # at 36% / 360 is exactly 50 of interest, a 0.10% hit on the 50,000 book.
    series = comparison.levered_market_reference
    assert series.points[-1].value == D("49950")
    assert series.return_percent == D("-0.10")
    assert "36.00%" in series.method_note


def test_levered_spy_takes_the_same_deposit_as_idle_cash() -> None:
    comparison = build_performance_comparison(
        balance_history=(
            _balance("2026-08-11T20:00:00+00:00", "50000", "50000"),
            _balance("2026-08-12T20:00:00+00:00", "75000", "50000"),
        ),
        cash_movements=(
            {
                "occurred_at": datetime(2026, 8, 12, 18, tzinfo=UTC),
                "movement_type": "transfer",
                "amount": D("25000"),
            },
        ),
        position_history=(_lot("KTOS", "500", "2026-08-11T20:00:00+00:00"),),
        daily_bars=(
            *_bars("KTOS", ("2026-08-11", "100"), ("2026-08-12", "100")),
            *_bars("SPY", ("2026-08-11", "100"), ("2026-08-12", "100")),
        ),
        margin_interest_rate_percent=D("0"),
    )

    series = comparison.levered_market_reference
    assert series.points[-1].external_flow == D("25000")
    assert series.points[-1].value == D("75000")
    assert series.return_percent == D("0")


def test_after_close_owner_flow_enters_benchmarks_on_the_next_session() -> None:
    comparison = build_performance_comparison(
        balance_history=(
            _balance("2026-08-11T20:00:00+00:00", "100000", "100000"),
            _balance("2026-08-12T20:00:00+00:00", "100000", "100000"),
            _balance("2026-08-13T20:00:00+00:00", "125000", "100000"),
        ),
        cash_movements=(
            {
                "occurred_at": datetime(2026, 8, 12, 21, tzinfo=UTC),
                "movement_type": "transfer",
                "amount": D("25000"),
            },
        ),
        position_history=(_lot("KTOS", "500", "2026-08-11T20:00:00+00:00"),),
        daily_bars=(
            *_bars(
                "KTOS",
                ("2026-08-11", "100"),
                ("2026-08-12", "100"),
                ("2026-08-13", "100"),
            ),
            *_bars(
                "SPY",
                ("2026-08-11", "100"),
                ("2026-08-12", "100"),
                ("2026-08-13", "100"),
            ),
        ),
        margin_interest_rate_percent=D("0"),
    )

    assert [point.external_flow for point in comparison.actual.points] == [
        D("0"),
        D("0"),
        D("25000"),
    ]
    assert [point.external_flow for point in comparison.shares_without_options.points] == [
        D("0"),
        D("0"),
        D("25000"),
    ]
    assert comparison.shares_without_options.return_percent == D("0")


def test_share_counterfactual_fails_closed_for_multiple_accounts() -> None:
    first = {**_lot("KTOS", "100", "2026-08-11T20:00:00+00:00"), "account_id": "a"}
    second = {
        **_lot("INTC", "100", "2026-08-11T20:00:00+00:00"),
        "account_id": "b",
        "account_mask": "...5678",
    }
    comparison = build_performance_comparison(
        balance_history=(
            _balance("2026-08-11T20:00:00+00:00", "100000", "100000"),
            _balance("2026-08-12T20:00:00+00:00", "101000", "100000"),
        ),
        cash_movements=(),
        position_history=(first, second),
        daily_bars=(
            *_bars("KTOS", ("2026-08-11", "100"), ("2026-08-12", "101")),
            *_bars("INTC", ("2026-08-11", "20"), ("2026-08-12", "21")),
            *_bars("SPY", ("2026-08-11", "640"), ("2026-08-12", "641")),
        ),
    )

    assert comparison.shares_without_options.status == "not_available"
    assert "multiple accounts" in comparison.shares_without_options.method_note
    assert comparison.levered_market_reference.status == "not_available"


def test_share_counterfactual_does_not_backfill_a_future_opening_snapshot() -> None:
    comparison = build_performance_comparison(
        balance_history=(
            _balance("2026-08-11T20:00:00+00:00", "100000", "100000"),
            _balance("2026-08-12T20:00:00+00:00", "101000", "100000"),
        ),
        cash_movements=(),
        position_history=(_lot("KTOS", "100", "2026-08-12T20:00:00+00:00"),),
        daily_bars=(
            *_bars("KTOS", ("2026-08-11", "100"), ("2026-08-12", "101")),
            *_bars("SPY", ("2026-08-11", "640"), ("2026-08-12", "641")),
        ),
    )

    assert comparison.shares_without_options.status == "not_available"
    assert "starts after" in comparison.shares_without_options.method_note


def _lot(symbol: str, quantity: str, observed: str) -> dict[str, object]:
    return {
        "sync_run_id": "run-1",
        "account_mask": "...1234",
        "observed_at": datetime.fromisoformat(observed),
        "symbol": symbol,
        "asset_type": "EQUITY",
        "net_quantity": D(quantity),
    }


def _bars(symbol: str, *closes: tuple[str, str]) -> tuple[dict[str, object], ...]:
    return tuple(
        {"symbol": symbol, "trade_date": date.fromisoformat(day), "close": D(close)}
        for day, close in closes
    )


def _balance(observed: str, liquidation: str, initial: str) -> dict[str, object]:
    return {
        "account_mask": "...1234",
        "observed_at": datetime.fromisoformat(observed),
        "liquidation_value": D(liquidation),
        "initial_liquidation_value": D(initial),
    }


def _run_balance(
    run_id: str,
    observed: str,
    liquidation: str,
    account_id: str = "account-a",
) -> dict[str, object]:
    return {
        "sync_run_id": run_id,
        "account_id": account_id,
        "account_mask": "...1234" if account_id == "account-a" else "...5678",
        "observed_at": datetime.fromisoformat(observed),
        "liquidation_value": D(liquidation),
        "initial_liquidation_value": D(liquidation),
    }
