from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

_OCC_TAIL = re.compile(r"^(?P<date>\d{6})(?P<type>[CP])(?P<strike>\d{8})$")


@dataclass(frozen=True, slots=True)
class ParsedOptionSymbol:
    underlying_symbol: str
    expiration_date: date
    option_type: str
    strike: Decimal


def parse_occ_option_symbol(symbol: str) -> ParsedOptionSymbol | None:
    """Parse the fixed-width OCC tail while preserving roots containing punctuation."""

    normalized = symbol.strip()
    if len(normalized) <= 15:
        return None
    root = normalized[:-15].strip()
    match = _OCC_TAIL.fullmatch(normalized[-15:])
    if not root or match is None:
        return None
    encoded_date = match.group("date")
    try:
        expiration = date(
            2000 + int(encoded_date[0:2]),
            int(encoded_date[2:4]),
            int(encoded_date[4:6]),
        )
    except ValueError:
        return None
    return ParsedOptionSymbol(
        underlying_symbol=root,
        expiration_date=expiration,
        option_type="CALL" if match.group("type") == "C" else "PUT",
        strike=Decimal(match.group("strike")) / Decimal("1000"),
    )
