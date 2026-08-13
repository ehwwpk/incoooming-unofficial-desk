from datetime import UTC, date, datetime
from decimal import Decimal

from schwab_dashboard.application.campaigns import (
    CampaignLinkConfidence,
    reconcile_option_campaigns,
)

D = Decimal


def test_exact_roll_keeps_one_campaign_across_contracts() -> None:
    rows = (
        _execution("open-one", "order-1", "CALL-65", "sell", "opening", "200", 1),
        _execution("close-one", "roll-1", "CALL-65", "buy", "closing", "-50", 2),
        _execution("open-two", "roll-1", "CALL-70", "sell", "opening", "125", 2),
        _execution("close-two", "close-2", "CALL-70", "buy", "closing", "-25", 3),
    )

    ledger = reconcile_option_campaigns(rows, ())

    assert len(ledger.campaigns) == 1
    campaign = ledger.campaigns[0]
    assert campaign.campaign_label == "C1"
    assert campaign.event_keys == ("open-one", "close-one", "open-two", "close-two")
    assert campaign.net_cash_to_date == D("250")
    assert campaign.status == "CLOSED"
    assert campaign.confidence is CampaignLinkConfidence.EXACT
    assert [item.net_cash_to_date for item in ledger.annotations] == [
        D("200"),
        D("150"),
        D("275"),
        D("250"),
    ]


def test_unmatched_resolution_is_visible_as_unknown() -> None:
    lifecycle = (
        {
            "external_key": "orphan-expiry",
            "occurred_at": date(2026, 8, 14),
            "event_type": "expiration",
            "symbol": "PUT-50",
            "underlying_symbol": "KTOS",
            "option_side": "put",
        },
    )

    ledger = reconcile_option_campaigns((), lifecycle)

    assert ledger.campaigns[0].campaign_label == "P1"
    assert ledger.campaigns[0].confidence is CampaignLinkConfidence.UNKNOWN
    assert ledger.annotation_for("orphan-expiry").confidence is CampaignLinkConfidence.UNKNOWN  # type: ignore[union-attr]


def test_partial_close_leaves_the_campaign_open() -> None:
    rows = (
        _execution("open", "open-order", "CALL-65", "sell", "opening", "800", 1, 4),
        _execution("close", "close-order", "CALL-65", "buy", "closing", "-100", 2, 2),
    )

    ledger = reconcile_option_campaigns(rows, ())

    assert len(ledger.campaigns) == 1
    assert ledger.campaigns[0].status == "OPEN"
    assert ledger.campaigns[0].confidence is CampaignLinkConfidence.EXACT


def test_overlapping_identical_contracts_do_not_get_a_fake_exact_link() -> None:
    rows = (
        _execution("open-a", "order-a", "CALL-65", "sell", "opening", "200", 1, 1),
        _execution("open-b", "order-b", "CALL-65", "sell", "opening", "210", 2, 1),
        _execution("close", "order-c", "CALL-65", "buy", "closing", "-50", 3, 1),
    )

    ledger = reconcile_option_campaigns(rows, ())

    close = ledger.annotation_for("close")
    assert close is not None
    assert close.confidence is CampaignLinkConfidence.UNKNOWN
    assert close.campaign_id.startswith("unlinked:")
    assert sum(campaign.status == "OPEN" for campaign in ledger.campaigns) == 2


def _execution(
    key: str,
    order: str,
    symbol: str,
    side: str,
    effect: str,
    net_cash: str,
    day: int,
    quantity: int = 1,
) -> dict[str, object]:
    return {
        "external_key": key,
        "order_external_key": order,
        "occurred_at": datetime(2026, 8, day, 15, tzinfo=UTC),
        "side": side,
        "position_effect": effect,
        "net_cash": D(net_cash),
        "quantity": D(quantity),
        "asset_type": "option",
        "symbol": symbol,
        "underlying_symbol": "KTOS",
        "option_side": "call",
    }
