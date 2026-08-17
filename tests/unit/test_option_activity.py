from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from schwab_dashboard.application.dashboard.option_activity import (
    build_option_outcomes,
    build_recent_option_activity,
)

D = Decimal
AS_OF = date(2026, 8, 14)


def test_recent_activity_combines_an_auditable_roll_order() -> None:
    rows = (
        _execution(
            "close-old",
            "roll-1",
            symbol="CVX  260814C00200000",
            side="buy",
            effect="closing",
            strike="200",
            expiration=date(2026, 8, 14),
            net_cash="-75",
            quantity=2,
        ),
        _execution(
            "open-new",
            "roll-1",
            symbol="CVX  260821C00205000",
            side="sell",
            effect="opening",
            strike="205",
            expiration=date(2026, 8, 21),
            net_cash="90",
            quantity=2,
        ),
    )

    activity = build_recent_option_activity(rows, as_of=AS_OF)

    assert len(activity) == 1
    assert activity[0].action_label == "ROLLED CALL"
    assert activity[0].detail == "$200C AUG 14  /  2 CONTRACTS  ->  $205C AUG 21  /  2 CONTRACTS"
    assert activity[0].amount == D("15")
    assert activity[0].contracts == 2
    assert activity[0].tone == "roll"


def test_recent_activity_excludes_shares_and_keeps_standalone_put_sale() -> None:
    rows = (
        _execution(
            "put-open",
            "put-order",
            symbol="KTOS  260821P00060000",
            side="sell",
            effect="opening",
            option_side="put",
            strike="60",
            expiration=date(2026, 8, 21),
            net_cash="125",
        ),
        {
            **_execution(
                "shares",
                "share-order",
                symbol="KTOS",
                side="buy",
                effect="opening",
                strike="0",
                expiration=date(2026, 8, 21),
                net_cash="-6000",
            ),
            "asset_type": "equity",
        },
    )

    activity = build_recent_option_activity(rows, as_of=AS_OF)

    assert len(activity) == 1
    assert activity[0].symbol == "KTOS"
    assert activity[0].action_label == "SOLD PUT"
    assert activity[0].detail == "$60P AUG 21  /  1 CONTRACT"


def test_outcomes_separate_rolls_from_plain_buybacks_and_ignore_unrelated_lifecycle() -> None:
    rows = (
        _execution(
            "close-roll",
            "roll-1",
            symbol="CVX  260814C00200000",
            side="buy",
            effect="closing",
            strike="200",
            expiration=date(2026, 8, 14),
            net_cash="-75",
            quantity=2,
        ),
        _execution(
            "open-roll",
            "roll-1",
            symbol="CVX  260821C00205000",
            side="sell",
            effect="opening",
            strike="205",
            expiration=date(2026, 8, 21),
            net_cash="90",
            quantity=1,
        ),
        _execution(
            "plain-close",
            "close-2",
            symbol="CVX  260814C00200000",
            side="buy",
            effect="closing",
            strike="200",
            expiration=date(2026, 8, 14),
            net_cash="-10",
        ),
        _execution(
            "short-expired",
            "open-3",
            symbol="CVX  260807C00210000",
            side="sell",
            effect="opening",
            strike="210",
            expiration=date(2026, 8, 7),
            net_cash="20",
        ),
    )
    lifecycle = (
        _lifecycle("expired", "CVX  260807C00210000", "expiration", quantity=2),
        _lifecycle("assigned", "CVX  260821C00205000", "assignment", quantity=1),
        _lifecycle("unrelated-long", "CVX  260807P00150000", "expiration", quantity=9),
    )

    outcomes = build_option_outcomes(
        rows,
        lifecycle,
        as_of=AS_OF,
        open_call_contracts=4,
        open_put_contracts=2,
    )

    assert outcomes.rolled_contracts == 1
    assert outcomes.roll_orders == 1
    assert outcomes.bought_back_contracts == 2
    assert outcomes.expired_contracts == 2
    assert outcomes.assigned_contracts == 1
    assert outcomes.assignment_shares == 100
    assert outcomes.open_contracts == 6


def test_orderless_close_and_open_are_not_invented_as_a_roll() -> None:
    rows = (
        _execution(
            "close",
            "",
            symbol="URNM  260814C00056000",
            side="buy",
            effect="closing",
            strike="56",
            expiration=date(2026, 8, 14),
            net_cash="-80",
        ),
        _execution(
            "open",
            "",
            symbol="URNM  260821C00058000",
            side="sell",
            effect="opening",
            strike="58",
            expiration=date(2026, 8, 21),
            net_cash="95",
        ),
    )

    activity = build_recent_option_activity(rows, as_of=AS_OF)
    outcomes = build_option_outcomes(
        rows,
        (),
        as_of=AS_OF,
        open_call_contracts=1,
        open_put_contracts=0,
    )

    assert {item.action_label for item in activity} == {"CLOSED CALL", "SOLD CALL"}
    assert outcomes.rolled_contracts == 0
    assert outcomes.bought_back_contracts == 1


def _execution(
    external_key: str,
    order_key: str,
    *,
    symbol: str,
    side: str,
    effect: str,
    strike: str,
    expiration: date,
    net_cash: str,
    option_side: str = "call",
    quantity: int = 1,
) -> dict[str, object]:
    return {
        "account_mask": "••1234",
        "external_key": external_key,
        "order_external_key": order_key or None,
        "occurred_at": datetime(2026, 8, 14, 15, tzinfo=UTC),
        "side": side,
        "position_effect": effect,
        "net_cash": D(net_cash),
        "quantity": D(quantity),
        "asset_type": "option",
        "symbol": symbol,
        "underlying_symbol": (
            "CVX" if symbol.startswith("CVX") else "KTOS" if symbol.startswith("KTOS") else "URNM"
        ),
        "option_side": option_side,
        "strike": D(strike),
        "expiration_date": expiration,
    }


def _lifecycle(
    external_key: str,
    symbol: str,
    event_type: str,
    *,
    quantity: int,
) -> dict[str, object]:
    return {
        "external_key": external_key,
        "occurred_at": datetime(2026, 8, 14, 20, tzinfo=UTC),
        "symbol": symbol,
        "underlying_symbol": "CVX",
        "option_side": "call" if "C" in symbol[-9:] else "put",
        "event_type": event_type,
        "option_quantity": D(quantity),
        "stock_quantity": D(quantity * 100),
    }
