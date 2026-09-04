from decimal import Decimal

from schwab_dashboard.application.option_lifecycle import (
    contract_multiplier,
    delivered_share_quantity,
    delivered_shares,
    known_stock_deliverable,
    lifecycle_event_type,
    option_contracts,
    option_side,
)
from schwab_dashboard.application.values import optional_bool

D = Decimal


def test_optional_bool_does_not_treat_false_text_as_true() -> None:
    assert optional_bool(False) is False
    assert optional_bool("False") is False
    assert optional_bool("yes") is True
    assert optional_bool("") is None
    assert optional_bool("unknown") is None


def test_lifecycle_aliases_and_enum_style_values_normalize() -> None:
    assert lifecycle_event_type(" Assigned ") == "assignment"
    assert lifecycle_event_type("OptionLifecycleType.EXERCISE") == "exercise"
    assert lifecycle_event_type("expired") == "expiration"
    assert lifecycle_event_type("adjustment") is None
    assert option_side("OptionSide.CALL") == "call"
    assert option_side(" p ") == "put"
    assert option_side("unknown") is None


def test_delivery_prefers_reported_shares_then_multiplier_then_standard_fallback() -> None:
    exact = {
        "option_quantity": D("2"),
        "stock_quantity": D("125"),
        "contract_multiplier": D("150"),
    }
    adjusted = {"option_quantity": D("2"), "contract_multiplier": D("150")}
    fallback = {"option_quantity": D("2")}

    assert delivered_share_quantity(exact) == D("125")
    assert delivered_shares({**exact, "stock_quantity": D("125.5")}) == D("125.5")
    assert delivered_share_quantity(adjusted) == D("300")
    assert delivered_share_quantity(fallback) == D("200")
    assert contract_multiplier({"multiplier": D("10")}) == D("10")
    assert contract_multiplier({"multiplier": D("-10")}) == D("10")
    assert option_contracts({"option_quantity": D("-2")}) == 2


def test_stock_deliverable_requires_standard_or_conventional_contract_evidence() -> None:
    standard = {
        "symbol": "KTOS  260918C00075000",
        "underlying_symbol": "KTOS",
        "contract_multiplier": D("100"),
    }
    adjusted = {
        **standard,
        "symbol": "KTOS1 260918C00075000",
        "contract_multiplier": D("150"),
        "is_non_standard": True,
    }
    structured = {
        "underlying_symbol": "XYZ",
        "deliverable": {
            "kind": "standard",
            "components": [
                {
                    "asset_type": "equity",
                    "symbol": "XYZ",
                    "quantity": "10",
                }
            ],
        },
    }

    assert known_stock_deliverable(standard) == D("100")
    assert known_stock_deliverable(adjusted) is None
    assert known_stock_deliverable(structured) == D("10")
