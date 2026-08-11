from datetime import date
from decimal import Decimal

from schwab_dashboard.infrastructure.schwab.option_symbol import parse_occ_option_symbol


def test_parses_padded_occ_call_symbol() -> None:
    parsed = parse_occ_option_symbol("KTOS  260918C00075000")

    assert parsed is not None
    assert parsed.underlying_symbol == "KTOS"
    assert parsed.expiration_date == date(2026, 9, 18)
    assert parsed.option_type == "CALL"
    assert parsed.strike == Decimal("75")


def test_refuses_invalid_occ_tail() -> None:
    assert parse_occ_option_symbol("NOT-AN-OPTION") is None
