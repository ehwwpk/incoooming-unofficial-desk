from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal

from schwab_dashboard.application.campaigns import CampaignLinkConfidence
from schwab_dashboard.application.dashboard.live_campaigns import project_campaign_summaries
from schwab_dashboard.application.dashboard.live_positions import build_live_position_book
from schwab_dashboard.application.dashboard.models import PositionSummary
from schwab_dashboard.web.rendering import templates

D = Decimal


def test_same_order_roll_is_one_campaign_with_both_legs() -> None:
    rows = (
        _execution(
            "open-one", "order-1", "KTOS  260814C00065000", "sell", "opening", "200", 1, strike="65"
        ),
        _execution(
            "close-one", "roll-1", "KTOS  260814C00065000", "buy", "closing", "-50", 2, strike="65"
        ),
        _execution(
            "open-two",
            "roll-1",
            "KTOS  260918C00070000",
            "sell",
            "opening",
            "125",
            2,
            strike="70",
            expires=date(2026, 9, 18),
        ),
        _execution(
            "close-two",
            "close-2",
            "KTOS  260918C00070000",
            "buy",
            "closing",
            "-25",
            3,
            strike="70",
            expires=date(2026, 9, 18),
        ),
    )

    campaigns = project_campaign_summaries(rows, (), live_book=None, as_of=date(2026, 8, 18))

    assert len(campaigns) == 1
    campaign = campaigns[0]
    assert campaign.campaign_label == "C1"
    assert campaign.status == "CLOSED"
    assert campaign.confidence == CampaignLinkConfidence.EXACT.value
    assert campaign.intent_label == "SHORT CALL"
    assert campaign.net_cash_to_date == D("250")
    assert campaign.initial_strike == D("65")
    assert campaign.current_strike == D("70")
    assert campaign.strike_change == D("5")
    assert campaign.days_extended == 35
    assert campaign.progress_percent == 100
    assert len(campaign.legs) == 4
    assert "ROLLED" not in campaign.status


def test_split_order_close_and_open_are_two_campaigns() -> None:
    rows = (
        _execution(
            "open-one", "order-a", "KTOS  260814C00065000", "sell", "opening", "200", 1, strike="65"
        ),
        _execution(
            "close-one", "order-b", "KTOS  260814C00065000", "buy", "closing", "-50", 2, strike="65"
        ),
        _execution(
            "open-two",
            "order-c",
            "KTOS  260918C00070000",
            "sell",
            "opening",
            "125",
            3,
            strike="70",
            expires=date(2026, 9, 18),
        ),
    )

    campaigns = project_campaign_summaries(rows, (), live_book=None, as_of=date(2026, 8, 18))

    assert len(campaigns) == 2
    assert {item.status for item in campaigns} == {"CLOSED", "OPEN"}
    assert all(item.campaign_label.startswith("C") for item in campaigns)
    open_campaign = next(item for item in campaigns if item.status == "OPEN")
    assert open_campaign.progress_percent == 0
    assert open_campaign.open_mark_profit_loss is None
    assert all("OPEN" not in leg for leg in open_campaign.legs)


def test_put_campaign_uses_assignment_notional_and_put_intent() -> None:
    rows = (
        _execution(
            "put-open",
            "put-1",
            "URNM  260918P00050000",
            "sell",
            "opening",
            "120",
            1,
            strike="50",
            expires=date(2026, 9, 18),
            option_side="put",
            underlying="URNM",
        ),
    )

    campaigns = project_campaign_summaries(rows, (), live_book=None, as_of=date(2026, 8, 18))

    assert len(campaigns) == 1
    campaign = campaigns[0]
    assert campaign.campaign_label == "P1"
    assert campaign.option_side == "put"
    assert campaign.intent_label == "SHORT PUT"
    assert campaign.collateral == D("5000")
    assert campaign.status == "OPEN"
    assert campaign.progress_percent == 0
    assert campaign.open_mark_profit_loss is None


def test_adjusted_put_campaign_withholds_collateral_when_delivery_is_unknown() -> None:
    adjusted = _execution(
        "put-open",
        "put-1",
        "URNM1 260918P00050000",
        "sell",
        "opening",
        "180",
        1,
        strike="50",
        expires=date(2026, 9, 18),
        option_side="put",
        underlying="URNM",
    )
    adjusted["contract_multiplier"] = D("150")
    adjusted["is_non_standard"] = True

    campaign = project_campaign_summaries(
        (adjusted,),
        (),
        live_book=None,
        as_of=date(2026, 8, 18),
    )[0]

    assert campaign.collateral is None
    assert campaign.cash_on_capital_percent is None


def test_overlapping_lots_surface_inferred_confidence() -> None:
    rows = (
        _execution(
            "open-a", "order-a", "KTOS  260918C00065000", "sell", "opening", "200", 1, strike="65"
        ),
        _execution(
            "open-b", "order-b", "KTOS  260918C00065000", "sell", "opening", "210", 2, strike="65"
        ),
        _execution(
            "close", "order-c", "KTOS  260918C00065000", "buy", "closing", "-50", 3, strike="65"
        ),
    )

    campaigns = project_campaign_summaries(rows, (), live_book=None, as_of=date(2026, 8, 18))

    assert len(campaigns) == 1
    assert campaigns[0].confidence == CampaignLinkConfidence.INFERRED.value
    assert campaigns[0].status == "OPEN"


def test_open_lot_mark_attaches_only_when_one_campaign_owns_the_line() -> None:
    option_symbol = "KTOS  260918C00075000"
    rows = (
        _execution(
            "open", "order-1", option_symbol, "sell", "opening", "245", 1, strike="75", quantity=5
        ),
    )
    book = build_live_position_book(
        (
            _equity(),
            _short_call(option_symbol, contracts=5, strike=D("75"), open_profit_loss=D("-425")),
        ),
        as_of=date(2026, 8, 18),
        executions=rows,
    )

    campaigns = project_campaign_summaries(rows, (), live_book=book, as_of=date(2026, 8, 18))

    assert len(campaigns) == 1
    campaign = campaigns[0]
    assert campaign.status == "OPEN"
    assert campaign.open_mark_profit_loss == D("-425")
    assert any("OPEN" in leg for leg in campaign.legs)
    assert campaign.collateral == D("60") * D("5") * D("100")


def test_open_leg_label_survives_occ_spacing() -> None:
    execution_symbol = "KTOS  260918C00075000"
    position_symbol = "KTOS 260918C00075000"
    rows = (
        _execution(
            "open",
            "order-1",
            execution_symbol,
            "sell",
            "opening",
            "245",
            1,
            strike="75.0000000000",
            quantity=5,
        ),
    )
    book = build_live_position_book(
        (
            _equity(),
            _short_call(position_symbol, contracts=5, strike=D("75"), open_profit_loss=D("-425")),
        ),
        as_of=date(2026, 8, 18),
        executions=rows,
    )

    campaigns = project_campaign_summaries(rows, (), live_book=book, as_of=date(2026, 8, 18))

    assert len(campaigns) == 1
    assert campaigns[0].open_mark_profit_loss == D("-425")
    assert any("OPEN" in leg for leg in campaigns[0].legs)
    assert any("$75C" in leg for leg in campaigns[0].legs)


def test_live_lot_spanning_two_campaigns_is_not_marked() -> None:
    occ = "KTOS  260918C00065000"
    rows = (
        _execution(
            "open-a",
            "open-a",
            "KTOS  260814C00060000",
            "sell",
            "opening",
            "100",
            1,
            strike="60",
        ),
        _execution(
            "close-a",
            "roll-a",
            "KTOS  260814C00060000",
            "buy",
            "closing",
            "-25",
            2,
            strike="60",
        ),
        _execution(
            "next-a",
            "roll-a",
            occ,
            "sell",
            "opening",
            "80",
            2,
            strike="65",
            expires=date(2026, 9, 18),
        ),
        _execution(
            "open-b",
            "open-b",
            "KTOS  260814C00062000",
            "sell",
            "opening",
            "100",
            3,
            strike="62",
        ),
        _execution(
            "close-b",
            "roll-b",
            "KTOS  260814C00062000",
            "buy",
            "closing",
            "-25",
            4,
            strike="62",
        ),
        _execution(
            "next-b",
            "roll-b",
            occ,
            "sell",
            "opening",
            "80",
            4,
            strike="65",
            expires=date(2026, 9, 18),
        ),
    )
    book = build_live_position_book(
        (
            _equity(),
            _short_call(occ, contracts=2, strike=D("65"), open_profit_loss=D("-100")),
        ),
        as_of=date(2026, 8, 18),
        executions=rows,
    )

    campaigns = project_campaign_summaries(rows, (), live_book=book, as_of=date(2026, 8, 18))
    open_campaigns = tuple(item for item in campaigns if item.status == "OPEN")

    assert len(open_campaigns) == 2
    assert all(item.open_mark_profit_loss is None for item in open_campaigns)
    assert all(all("OPEN" not in leg for leg in item.legs) for item in open_campaigns)


def test_mark_does_not_mix_accounts_on_the_same_occ() -> None:
    occ = "KTOS  260918C00075000"
    rows = (
        _execution(
            "ours",
            "order-ours",
            occ,
            "sell",
            "opening",
            "245",
            1,
            strike="75",
            quantity=5,
            account_mask="...1234",
        ),
        _execution(
            "theirs",
            "order-theirs",
            occ,
            "sell",
            "opening",
            "210",
            2,
            strike="75",
            quantity=5,
            account_mask="...9999",
        ),
    )
    book = build_live_position_book(
        (
            _equity(),
            _short_call(occ, contracts=5, strike=D("75"), open_profit_loss=D("-425")),
        ),
        as_of=date(2026, 8, 18),
        executions=rows,
    )

    campaigns = project_campaign_summaries(rows, (), live_book=book, as_of=date(2026, 8, 18))
    ours = next(item for item in campaigns if "ours" in item.campaign_id)
    theirs = next(item for item in campaigns if "theirs" in item.campaign_id)

    assert ours.open_mark_profit_loss == D("-425")
    assert theirs.open_mark_profit_loss is None
    assert any("OPEN" in leg for leg in ours.legs)


def test_empty_ledger_projects_no_campaigns() -> None:
    assert project_campaign_summaries((), (), live_book=None, as_of=date(2026, 8, 18)) == ()


def test_long_option_lifecycle_is_not_a_campaign_card() -> None:
    rows = (
        _execution(
            "long-open",
            "order",
            "KTOS  260918C00065000",
            "buy",
            "opening",
            "-100",
            1,
            strike="65",
        ),
    )
    lifecycle = (
        {
            "external_key": "long-expiry",
            "occurred_at": date(2026, 8, 2),
            "event_type": "expiration",
            "option_quantity": D("1"),
            "symbol": "KTOS  260918C00065000",
            "underlying_symbol": "KTOS",
            "option_side": "call",
            "strike": D("65"),
            "expiration_date": date(2026, 9, 18),
        },
    )
    assert (
        project_campaign_summaries(rows, lifecycle, live_book=None, as_of=date(2026, 8, 18)) == ()
    )


def test_campaign_template_renames_heading_and_has_empty_state() -> None:
    from schwab_dashboard.infrastructure.demo.dashboard import DemoDashboardReader

    snapshot = DemoDashboardReader().execute()
    filled = templates.env.get_template("partials/_campaigns.html").render(snapshot=snapshot)
    open_count = sum(item.status == "OPEN" for item in snapshot.campaigns)
    closed_count = len(snapshot.campaigns) - open_count
    assert "<b>CAMPAIGNS</b>" in filled
    assert "data-campaigns-drawer" in filled
    assert (
        '<details class="workspace-panel results-disclosure campaigns-drawer" '
        'id="campaigns" data-campaigns-drawer>' in filled
    )
    assert "Call campaigns" not in filled
    assert "KTOS" in filled
    assert open_count == 6
    assert closed_count > 0
    assert f"{open_count} OPEN · {len(snapshot.campaigns)} TOTAL" in filled
    assert 'id="campaigns-open"' in filled
    assert ' data-workspace-section="campaigns-open" open>' in filled
    assert 'id="campaigns-closed"' in filled
    assert ' data-workspace-section="campaigns-closed">' in filled
    assert 'role="tablist"' not in filled
    assert "<b>OPEN</b>" in filled
    assert "<b>CLOSED</b>" in filled
    assert "NOT OPEN · CLOSED / EXPIRED / ASSIGNED" in filled
    assert "campaign-status assigned" in filled
    assert "campaign-status expired" in filled

    empty = templates.env.get_template("partials/_campaigns.html").render(
        snapshot=replace(snapshot, campaigns=()),
    )
    assert "No short-premium campaigns in this ledger." in empty
    assert "0 OPEN · 0 TOTAL" in empty
    assert 'id="campaigns-open"' not in empty
    assert 'id="campaigns-closed"' not in empty

    put = project_campaign_summaries(
        (
            _execution(
                "put-open",
                "put-1",
                "URNM  260918P00050000",
                "sell",
                "opening",
                "120",
                1,
                strike="50",
                expires=date(2026, 9, 18),
                option_side="put",
                underlying="URNM",
            ),
        ),
        (),
        live_book=None,
        as_of=date(2026, 8, 18),
    )
    put_html = templates.env.get_template("partials/_campaigns.html").render(
        snapshot=replace(snapshot, campaigns=put)
    )
    assert "CASH / ASSIGN. NOTIONAL" in put_html
    assert "P1" in put_html
    assert "SHORT PUT" in put_html
    assert 'id="campaigns-open"' in put_html
    assert 'id="campaigns-closed"' not in put_html

    closed_only = tuple(item for item in snapshot.campaigns if item.status != "OPEN")
    closed_html = templates.env.get_template("partials/_campaigns.html").render(
        snapshot=replace(snapshot, campaigns=closed_only)
    )
    assert 'id="campaigns-open"' not in closed_html
    assert ' data-workspace-section="campaigns-closed" open>' in closed_html
    assert f"0 OPEN · {len(closed_only)} TOTAL" in closed_html


def _execution(
    key: str,
    order: str,
    symbol: str,
    side: str,
    effect: str,
    net_cash: str,
    day: int,
    *,
    quantity: int = 1,
    strike: str = "65",
    expires: date = date(2026, 8, 14),
    option_side: str = "call",
    underlying: str = "KTOS",
    account_mask: str = "",
) -> dict[str, object]:
    cash = D(net_cash)
    payload: dict[str, object] = {
        "external_key": key,
        "order_external_key": order,
        "occurred_at": datetime(2026, 8, day, 15, tzinfo=UTC),
        "side": side,
        "position_effect": effect,
        "net_cash": cash,
        "gross_amount": abs(cash),
        "fees": D("0"),
        "quantity": D(quantity),
        "asset_type": "option",
        "symbol": symbol,
        "underlying_symbol": underlying,
        "option_side": option_side,
        "strike": D(strike),
        "expiration_date": expires,
        "contract_multiplier": D("100"),
    }
    if account_mask:
        payload["account_mask"] = account_mask
    return payload


def _equity() -> PositionSummary:
    return PositionSummary(
        account_mask="...1234",
        symbol="KTOS",
        description="Kratos Defense",
        asset_type="EQUITY",
        quantity=D("800"),
        average_price=D("40"),
        mark=D("60"),
        market_value=D("48000"),
        day_profit_loss=D("0"),
        day_profit_loss_percent=None,
        strategy=None,
    )


def _short_call(
    symbol: str,
    *,
    contracts: int,
    strike: Decimal,
    open_profit_loss: Decimal,
) -> PositionSummary:
    return PositionSummary(
        account_mask="...1234",
        symbol=symbol,
        description="KTOS call",
        asset_type="OPTION",
        quantity=-D(contracts),
        average_price=D("2.45"),
        mark=D("3.30"),
        market_value=D("-1650"),
        day_profit_loss=D("0"),
        day_profit_loss_percent=None,
        strategy="Short call",
        underlying_symbol="KTOS",
        option_type="CALL",
        expiration_date=date(2026, 9, 18),
        strike=strike,
        open_profit_loss=open_profit_loss,
        contract_multiplier=D("100"),
    )
