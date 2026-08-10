from decimal import Decimal

from schwab_dashboard.application.dashboard.cashflows import build_call_cash_events
from schwab_dashboard.infrastructure.demo.dashboard import DemoDashboardReader

D = Decimal


def test_cash_windows_and_charts_share_one_execution_ledger() -> None:
    snapshot = DemoDashboardReader().execute()
    windows = {item.key: item for item in snapshot.performance_windows}
    series = {item.key: item for item in snapshot.cash_chart_series}

    assert len(build_call_cash_events(snapshot.call_history)) == 24
    for key in ("month", "quarter", "ytd", "r365"):
        assert sum((point.option_cash for point in series[key].points), D("0")) == (
            windows[key].option_cash
        )
        assert sum((point.dividends for point in series[key].points), D("0")) == (
            windows[key].dividends
        )
    assert windows["month"].gross_premium == D("4240")
    assert windows["month"].buyback_cost == D("2435")
    assert windows["month"].option_cash == D("1805")
    assert len(series["month"].points) == 28


def test_open_campaigns_reconcile_roll_chains_and_marks() -> None:
    snapshot = DemoDashboardReader().execute()
    campaigns = {item.campaign_id: item for item in snapshot.campaigns}

    assert sum(item.status == "OPEN" for item in campaigns.values()) == 6
    for campaign in campaigns.values():
        assert campaign.net_cash_to_date == (
            campaign.gross_opening_credit - campaign.closing_debits - campaign.fees
        )
        assert campaign.open_mark_profit_loss == (
            campaign.open_credit - campaign.estimated_close_value
        )
    ktos = campaigns["ktos-roll-75"]
    assert ktos.initial_strike == D("60")
    assert ktos.current_strike == D("75")
    assert ktos.strike_change == D("15")
    assert ktos.days_extended == 21
    assert ktos.net_cash_to_date == D("1425")


def test_expiration_calendar_reconciles_every_open_obligation() -> None:
    snapshot = DemoDashboardReader().execute()

    assert sum(item.contracts for item in snapshot.expiration_calendar) == (
        snapshot.covered_calls.active_contracts
    )
    assert sum(item.committed_shares for item in snapshot.expiration_calendar) == 1800
    assert sum((item.opening_credit for item in snapshot.expiration_calendar), D("0")) == (
        snapshot.covered_calls.open_call_credit
    )
    assert (
        sum((item.estimated_close_value for item in snapshot.expiration_calendar), D("0"))
        == snapshot.covered_calls.open_call_mark_value
    )
    assert snapshot.expiration_calendar[0].days_to_expiration == 7
    assert snapshot.expiration_calendar[1].event_labels == ("CVX ex-dividend Aug 19",)


def test_attribution_refuses_unsupported_long_history() -> None:
    snapshot = DemoDashboardReader().execute()
    attribution = {item.key: item for item in snapshot.strategy_attribution}

    for key in ("month", "quarter"):
        row = attribution[key]
        assert row.actual_result is not None
        assert row.stock_only_result is not None
        assert row.active_management_difference == row.actual_result - row.stock_only_result
        assert row.status == "CURRENT-INVENTORY PROXY"
    for key in ("ytd", "r365"):
        assert attribution[key].actual_result is None
        assert "UNAVAILABLE" in attribution[key].status


def test_personal_policies_cover_declared_tranches_without_inventing_urnm_rules() -> None:
    snapshot = DemoDashboardReader().execute()
    policies = {item.symbol: item for item in snapshot.policies}

    assert policies["CVX"].governed_shares == 600
    assert policies["KTOS"].governed_shares == 800
    assert policies["URNM"].governed_shares == 400
    assert [item.label for item in policies["KTOS"].policies[:2]] == [
        "$75 short cycle",
        "$90 long cycle",
    ]
    assert "until a more specific policy is declared" in policies["URNM"].policies[0].note
