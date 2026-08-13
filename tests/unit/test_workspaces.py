from dataclasses import replace
from datetime import date
from decimal import Decimal

from schwab_dashboard.application.dashboard.live_positions import build_live_position_book
from schwab_dashboard.application.dashboard.models import PositionSummary
from schwab_dashboard.application.dashboard.overview import build_desk_overview
from schwab_dashboard.application.ports.brokerage_data import (
    BrokerageSourceProfile,
    BrokerCapability,
    CapabilityState,
    DataSourceKind,
)
from schwab_dashboard.application.workspaces.catalog import get_workspace, list_workspaces
from schwab_dashboard.application.workspaces.projections import (
    build_open_book,
    build_volatility_rows,
)
from schwab_dashboard.application.workspaces.source_profiles import planned_source_profiles
from schwab_dashboard.domain.workspace import WorkspaceKey
from schwab_dashboard.infrastructure.demo.dashboard import DemoDashboardReader


def test_workspace_catalog_keeps_stable_keys_separate_from_labels() -> None:
    workspaces = list_workspaces()

    assert [item.key for item in workspaces] == list(WorkspaceKey)
    assert len({item.route for item in workspaces}) == len(workspaces)
    assert len({item.window_name for item in workspaces}) == len(workspaces)
    assert get_workspace(WorkspaceKey.RISK).label == "Open Options"
    assert get_workspace(WorkspaceKey.ATTRIBUTION).label == "Results"
    assert get_workspace(WorkspaceKey.RECORDS).label == "Data Health"
    assert get_workspace(WorkspaceKey.RADAR).label == "Premium Radar"
    assert get_workspace(WorkspaceKey.RISK).route == "/workspaces/risk"
    assert get_workspace(WorkspaceKey.RECORDS).window_name == "iud-source-ledger"


def test_open_book_projection_reconciles_to_dashboard_open_mark() -> None:
    snapshot = DemoDashboardReader().execute()
    projection = build_open_book(snapshot)

    assert projection.entry_credit == snapshot.covered_calls.open_call_credit
    assert projection.current_liability == snapshot.covered_calls.open_call_mark_value
    assert projection.open_profit_loss == snapshot.covered_calls.open_mark_profit_loss
    assert projection.theta_estimate_per_day == snapshot.risk.daily_theta
    assert projection.obligated_shares == snapshot.covered_calls.active_contracts * 100
    assert tuple(row for group in projection.groups for row in group.rows) == projection.rows
    assert {group.symbol for group in projection.groups} == {
        item.symbol for item in snapshot.underlyings if item.open_call_clocks
    }


def test_open_book_exposes_exact_contract_clocks_and_bounded_value_track() -> None:
    snapshot = DemoDashboardReader().execute()
    projection = build_open_book(snapshot)

    assert projection.rows
    for row in projection.rows:
        assert row.original_days_to_expiration >= row.days_to_expiration
        assert row.sold_on <= row.expires_on
        assert Decimal(0) <= row.option_value_track_percent <= Decimal(100)
        assert row.option_value_overrun_percent == max(
            Decimal(0), row.option_value_vs_credit_percent - Decimal(100)
        )
    for group in projection.groups:
        assert group.contract_count == sum(row.contracts for row in group.rows)
        assert group.next_expiration_dte == min(
            row.days_to_expiration for row in group.rows
        )
        assert abs(group.nearest_buffer_percent) == min(
            abs(row.strike_distance_percent) for row in group.rows
        )


def test_desk_overview_prioritizes_the_nearest_live_call_without_losing_totals() -> None:
    snapshot = DemoDashboardReader().execute()
    overview = build_desk_overview(snapshot)

    assert overview.open_positions == 6
    assert overview.open_contracts == snapshot.covered_calls.active_contracts
    assert overview.open_mark_profit_loss == snapshot.covered_calls.open_mark_profit_loss
    assert overview.nearest_call is not None
    assert overview.nearest_call.symbol == "CVX"
    assert overview.nearest_call.strike == 195
    assert overview.next_expiring_option is not None
    assert overview.next_expiring_option.days_to_expiration == 7
    assert overview.nearest_call.anchor_id.startswith("option-")
    assert len(overview.position_rows) == len(snapshot.underlyings)
    assert sum(row.open_positions for row in overview.position_rows) == overview.open_positions


def test_desk_overview_includes_short_puts_without_corrupting_call_coverage() -> None:
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
    snapshot_with_put = replace(snapshot, live_position_book=live_book)
    overview = build_desk_overview(snapshot_with_put)
    open_book = build_open_book(snapshot_with_put)

    assert overview.open_put_positions == 1
    assert overview.open_put_contracts == 1
    assert overview.open_positions == 7
    assert overview.open_contracts == snapshot.covered_calls.active_contracts + 1
    assert overview.open_call_contracts == snapshot.covered_calls.active_contracts
    assert overview.coverage_percent == snapshot.covered_calls.coverage_percent
    assert overview.open_mark_profit_loss == snapshot.covered_calls.open_mark_profit_loss - 50
    assert open_book.put_contracts == 1
    assert open_book.call_contracts == snapshot.covered_calls.active_contracts
    assert open_book.total_contracts == snapshot.covered_calls.active_contracts + 1
    assert open_book.total_positions == len(open_book.rows) + 1
    assert open_book.put_rows[0].symbol == "URNM"
    assert open_book.put_rows[0].days_to_expiration == 42


def test_volatility_projection_uses_daily_closes_and_refuses_to_invent_iv_rank() -> None:
    snapshot = DemoDashboardReader().execute()
    rows = build_volatility_rows(snapshot)

    assert len(rows) == len(snapshot.underlyings)
    assert all(row.sessions == 58 for row in rows)
    assert all(row.realized_volatility_percent is not None for row in rows)
    assert all(row.iv_rank_percent is None for row in rows)
    assert all(row.quality == "partial" for row in rows)


def test_source_profiles_are_read_only_and_unknown_capabilities_fail_closed() -> None:
    profiles = planned_source_profiles()

    assert {profile.kind for profile in profiles} == {
        DataSourceKind.DIRECT_BROKER,
        DataSourceKind.AGGREGATOR,
        DataSourceKind.FILE_IMPORT,
    }
    assert all(profile.read_only for profile in profiles)
    assert all(
        profile.capability(BrokerCapability.TAX_LOTS).state is CapabilityState.UNKNOWN
        for profile in profiles
    )


def test_non_read_only_source_profile_is_rejected() -> None:
    try:
        BrokerageSourceProfile(
            source_key="unsafe",
            display_name="Unsafe",
            kind=DataSourceKind.DIRECT_BROKER,
            read_only=False,
            support=(),
        )
    except ValueError as exc:
        assert "read-only" in str(exc)
    else:
        raise AssertionError("a trading-capable source crossed the analytics boundary")
