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
    assert get_workspace(WorkspaceKey.RISK).label == "Open Calls"
    assert get_workspace(WorkspaceKey.ATTRIBUTION).label == "Strategy Review"
    assert get_workspace(WorkspaceKey.RECORDS).label == "Data Health"
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


def test_desk_overview_prioritizes_the_nearest_live_call_without_losing_totals() -> None:
    snapshot = DemoDashboardReader().execute()
    overview = build_desk_overview(snapshot)

    assert overview.open_positions == 5
    assert overview.open_contracts == snapshot.covered_calls.active_contracts
    assert overview.open_mark_profit_loss == snapshot.covered_calls.open_mark_profit_loss
    assert overview.nearest_call is not None
    assert overview.nearest_call.symbol == "KTOS"
    assert overview.nearest_call.strike == 65
    assert overview.next_expiring_call is not None
    assert overview.next_expiring_call.days_to_expiration == 28
    assert len(overview.position_rows) == len(snapshot.underlyings)
    assert sum(row.open_positions for row in overview.position_rows) == overview.open_positions


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
