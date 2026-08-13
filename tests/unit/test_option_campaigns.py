from datetime import UTC, date, datetime
from decimal import Decimal

from schwab_dashboard.application.campaigns import (
    CampaignLinkConfidence,
    reconcile_option_campaigns,
)
from schwab_dashboard.application.campaigns.audit import audit_campaign_ledger

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
    assert close.confidence is CampaignLinkConfidence.INFERRED
    assert len(ledger.campaigns) == 1
    assert ledger.campaigns[0].status == "OPEN"
    assert ledger.campaigns[0].confidence is CampaignLinkConfidence.INFERRED


def test_fifo_resolution_of_two_rolled_campaigns_is_visible_as_inferred() -> None:
    rows = (
        _execution("open-a", "open-a", "CALL-60", "sell", "opening", "100", 1),
        _execution("close-a", "roll-a", "CALL-60", "buy", "closing", "-25", 2),
        _execution("next-a", "roll-a", "CALL-65", "sell", "opening", "80", 2),
        _execution("open-b", "open-b", "CALL-62", "sell", "opening", "100", 3),
        _execution("close-b", "roll-b", "CALL-62", "buy", "closing", "-25", 4),
        _execution("next-b", "roll-b", "CALL-65", "sell", "opening", "80", 4),
        _execution("one-close", "close", "CALL-65", "buy", "closing", "-20", 5),
    )

    ledger = reconcile_option_campaigns(rows, ())
    close = ledger.annotation_for("one-close")

    assert close is not None
    assert close.confidence is CampaignLinkConfidence.INFERRED
    assert close.campaign_id == ledger.annotation_for("open-a").campaign_id  # type: ignore[union-attr]


def test_partial_assignment_keeps_remaining_contracts_open() -> None:
    rows = (_execution("open", "order", "CALL-65", "sell", "opening", "400", 1, 4),)
    lifecycle = (
        {
            "external_key": "partial-assignment",
            "occurred_at": date(2026, 8, 2),
            "event_type": "assignment",
            "option_quantity": D("1"),
            "symbol": "CALL-65",
            "underlying_symbol": "KTOS",
            "option_side": "call",
        },
    )

    ledger = reconcile_option_campaigns(rows, lifecycle)

    assert len(ledger.campaigns) == 1
    assert ledger.campaigns[0].status == "OPEN"
    assert ledger.campaigns[0].event_keys == ("open", "partial-assignment")


def test_long_option_expiration_is_excluded_from_short_premium_campaigns() -> None:
    rows = (_execution("long-open", "order", "CALL-65", "buy", "opening", "-100", 1),)
    lifecycle = (
        {
            "external_key": "long-expiry",
            "occurred_at": date(2026, 8, 2),
            "event_type": "expiration",
            "option_quantity": D("1"),
            "symbol": "CALL-65",
            "underlying_symbol": "KTOS",
            "option_side": "call",
        },
    )

    ledger = reconcile_option_campaigns(rows, lifecycle)

    assert ledger.campaigns == ()
    assert ledger.exclusion_for("long-expiry") is not None


def test_campaign_audit_holds_removal_gate_for_unknown_or_adjusted_history() -> None:
    lifecycle = (
        {
            "external_key": "orphan",
            "occurred_at": date(2026, 8, 2),
            "event_type": "assignment",
            "option_quantity": D("1"),
            "symbol": "CALL-65",
            "underlying_symbol": "KTOS",
            "option_side": "call",
            "contract_multiplier": D("10"),
        },
    )
    ledger = reconcile_option_campaigns((), lifecycle)

    audit = audit_campaign_ledger(ledger, (), lifecycle)

    assert audit.unknown_campaigns == 1
    assert audit.adjusted_contract_events == 1
    assert audit.legacy_removal_gate_passed is False


def test_campaign_audit_proves_campaign_cash_matches_atomic_short_option_cash() -> None:
    rows = (
        _execution("open", "order-a", "CALL-65", "sell", "opening", "250", 1),
        _execution("close", "order-b", "CALL-65", "buy", "closing", "-75", 2),
        _execution("long", "order-c", "CALL-90", "buy", "opening", "-40", 3),
    )

    audit = audit_campaign_ledger(reconcile_option_campaigns(rows, ()), rows, ())

    assert audit.source_net_cash == D("175")
    assert audit.campaign_net_cash == D("175")
    assert audit.cash_variance == D("0")
    assert audit.legacy_removal_gate_passed is True


def test_adjusted_contract_assignment_remains_auditable_without_assuming_100_shares() -> None:
    rows = (_execution("open", "order-a", "ADJUSTED-CALL", "sell", "opening", "75", 1),)
    lifecycle = (
        {
            "external_key": "adjusted-assignment",
            "occurred_at": date(2026, 8, 2),
            "event_type": "assignment",
            "option_quantity": D("1"),
            "symbol": "ADJUSTED-CALL",
            "underlying_symbol": "KTOS",
            "option_side": "call",
            "contract_multiplier": D("10"),
            "deliverable": {"kind": "adjusted", "description": "10 shares plus cash"},
        },
    )

    ledger = reconcile_option_campaigns(rows, lifecycle)
    audit = audit_campaign_ledger(ledger, rows, lifecycle)

    assert len(ledger.campaigns) == 1
    assert ledger.campaigns[0].status == "ASSIGNED"
    assert ledger.campaigns[0].event_keys == ("open", "adjusted-assignment")
    assert audit.adjusted_contract_events == 1
    assert audit.cash_variance == D("0")
    assert audit.legacy_removal_gate_passed is True


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
