from decimal import Decimal
from types import SimpleNamespace

from schwab_dashboard.infrastructure.database.analytics_reader import (
    _canonical_option_metadata,
    _instrument_option_metadata,
    _position_option_metadata,
)


class _Session:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self.rows = rows

    def execute(self, _query: object) -> list[tuple[object, ...]]:
        return self.rows


def test_chain_metadata_enriches_account_position_by_canonical_occ_symbol() -> None:
    metadata = _canonical_option_metadata(
        _Session(
            [
                ("KTOS  260918C00075000", Decimal("100"), {"kind": "standard"}),
                ("KTOS  260918C00075000", Decimal("100"), {"kind": "unknown"}),
            ]
        )
    )
    position = SimpleNamespace(
        asset_type="OPTION",
        symbol="KTOS   260918C00075000",
        contract_multiplier=None,
        is_non_standard=None,
    )

    assert _position_option_metadata(position, None, metadata) == (Decimal("100"), False)


def test_conflicting_chain_contract_terms_are_not_used_as_position_facts() -> None:
    metadata = _canonical_option_metadata(
        _Session(
            [
                ("KTOS  260918C00075000", Decimal("100"), {"kind": "standard"}),
                ("KTOS  260918C00075000", Decimal("150"), {"kind": "adjusted"}),
            ]
        )
    )
    position = SimpleNamespace(
        asset_type="OPTION",
        symbol="KTOS  260918C00075000",
        contract_multiplier=None,
        is_non_standard=None,
    )

    assert _position_option_metadata(position, None, metadata) == (None, None)


def test_chain_metadata_enriches_execution_instrument_by_canonical_occ_symbol() -> None:
    instrument = SimpleNamespace(
        asset_type="OPTION",
        symbol="CVX   261009C00225000",
        contract_multiplier=Decimal("100"),
        deliverable={"kind": "unknown"},
    )
    metadata = {"CVX261009C00225000": (Decimal("100"), False)}

    assert _instrument_option_metadata(instrument, metadata) == (Decimal("100"), False)
