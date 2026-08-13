from __future__ import annotations

import re
from datetime import UTC, date, datetime
from decimal import Decimal

from schwab_dashboard.infrastructure.schwab.option_symbol import parse_occ_option_symbol

_DATE_DESCRIPTION = re.compile(
    r"(?P<underlying>[A-Z][A-Z0-9.]{0,8})\s+"
    r"(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s+"
    r"(?P<strike>\d+(?:\.\d+)?)\s*(?P<side>CALL|PUT|C|P)\b",
    re.IGNORECASE,
)
_MONTH_DESCRIPTION = re.compile(
    r"(?P<underlying>[A-Z][A-Z0-9.]{0,8})\s+"
    r"(?P<month>JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+"
    r"(?P<day>\d{1,2})\s+(?P<year>\d{4})\s+"
    r"(?P<strike>\d+(?:\.\d+)?)\s*(?P<side>CALL|PUT|C|P)\b",
    re.IGNORECASE,
)
_COMPACT = re.compile(
    r"^-?(?P<underlying>[A-Z.]+?)(?P<date>\d{6})(?P<side>[CP])(?P<strike>\d+(?:\.\d+)?)$",
    re.IGNORECASE,
)


def option_metadata(*, symbol: str, description: str) -> dict[str, str] | None:
    clean_symbol = "".join(symbol.upper().split())
    parsed = parse_occ_option_symbol(symbol) or parse_occ_option_symbol(clean_symbol)
    if parsed is not None:
        return _payload(
            underlying=parsed.underlying_symbol,
            expiration=parsed.expiration_date,
            side=parsed.option_type,
            strike=parsed.strike,
            occ_symbol=symbol.strip() or clean_symbol,
        )
    compact = _COMPACT.match(clean_symbol)
    if compact is not None:
        try:
            expiration = datetime.strptime(compact.group("date"), "%y%m%d").date()
            return _payload(
                underlying=compact.group("underlying"),
                expiration=expiration,
                side="CALL" if compact.group("side").upper() == "C" else "PUT",
                strike=Decimal(compact.group("strike")),
            )
        except ValueError:
            pass
    combined = f"{symbol} {description}".upper()
    match = _DATE_DESCRIPTION.search(combined)
    if match is not None:
        expiration = _date(match.group("date"))
        return _payload(
            underlying=match.group("underlying"),
            expiration=expiration,
            side=_side(match.group("side")),
            strike=Decimal(match.group("strike")),
        )
    match = _MONTH_DESCRIPTION.search(combined)
    if match is not None:
        expiration = datetime.strptime(
            f"{match.group('month')} {match.group('day')} {match.group('year')}",
            "%b %d %Y",
        ).date()
        return _payload(
            underlying=match.group("underlying"),
            expiration=expiration,
            side=_side(match.group("side")),
            strike=Decimal(match.group("strike")),
        )
    return None


def contract_multiplier(
    *, explicit: Decimal | None, symbol: str, description: str, is_option: bool
) -> tuple[Decimal | None, str | None]:
    if not is_option:
        return None, None
    if explicit is not None and explicit > 0:
        return explicit, "exported"
    signal = f"{symbol} {description}".upper()
    if any(token in signal for token in ("ADJUSTED", " ADJ ", "NON-STANDARD", "NONSTANDARD")):
        return None, "unknown_adjusted"
    return Decimal("100"), "assumed_standard"


def _payload(
    *,
    underlying: str,
    expiration: date,
    side: str,
    strike: Decimal,
    occ_symbol: str | None = None,
) -> dict[str, str]:
    symbol = occ_symbol or (
        f"{underlying.upper():<6}{expiration:%y%m%d}{side[0]}{int(strike * Decimal('1000')):08d}"
    )
    return {
        "occ_symbol": symbol,
        "underlying_symbol": underlying.upper(),
        "option_type": side,
        "expiration_date": expiration.isoformat(),
        "strike": str(strike),
    }


def _date(value: str) -> date:
    for pattern in ("%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.strptime(value, pattern).replace(tzinfo=UTC).date()
        except ValueError:
            pass
    raise ValueError(value)


def _side(value: str) -> str:
    return "CALL" if value.upper() in {"C", "CALL"} else "PUT"
