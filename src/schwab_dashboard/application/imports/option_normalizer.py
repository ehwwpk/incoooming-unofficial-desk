from __future__ import annotations

import re
from datetime import UTC, date, datetime
from decimal import Decimal

from schwab_dashboard.infrastructure.schwab.option_symbol import parse_occ_option_symbol

_DATE_DESCRIPTION = re.compile(
    r"(?P<underlying>[A-Z][A-Z0-9.]{0,8})\s+"
    r"(?P<date>\d{1,2}/\d{1,2}/\d{2,4})\s+"
    r"(?:\$?(?P<strike>\d+(?:\.\d+)?)\s*(?P<side>CALL|PUT|C|P)\b|"
    r"(?P<side_first>CALL|PUT|C|P)\s+\$?(?P<strike_after>\d+(?:\.\d+)?)\b)",
    re.IGNORECASE,
)
_MONTH_DESCRIPTION = re.compile(
    r"(?P<underlying>[A-Z][A-Z0-9.]{0,8})\s+"
    r"(?P<month>JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+"
    r"(?P<day>\d{1,2})\s+(?P<year>\d{4})\s+"
    r"(?:\$?(?P<strike>\d+(?:\.\d+)?)\s*(?P<side>CALL|PUT|C|P)\b|"
    r"(?P<side_first>CALL|PUT|C|P)\s+\$?(?P<strike_after>\d+(?:\.\d+)?)\b)",
    re.IGNORECASE,
)
_DAY_MONTH_DESCRIPTION = re.compile(
    r"(?P<underlying>[A-Z][A-Z0-9.]{0,8})\s+"
    r"(?P<day>\d{1,2})\s*"
    r"(?P<month>JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s*"
    r"(?P<year>\d{2}|\d{4})\s+"
    r"(?:\$?(?P<strike>\d+(?:\.\d+)?)\s*(?P<side>CALL|PUT|C|P)\b|"
    r"(?P<side_first>CALL|PUT|C|P)\s+\$?(?P<strike_after>\d+(?:\.\d+)?)\b)",
    re.IGNORECASE,
)
_COMPACT = re.compile(
    r"^-?(?P<underlying>[A-Z.]+?)(?P<date>\d{6})(?P<side>[CP])(?P<strike>\d+(?:\.\d+)?)$",
    re.IGNORECASE,
)
_OPTION_WORD = re.compile(r"\b(?:CALL|PUT|OPTION)\b", re.IGNORECASE)
_EQUITY_SYMBOL = re.compile(r"[A-Z][A-Z.]{0,8}\Z", re.IGNORECASE)
_FUND_DESCRIPTION = re.compile(r"\b(?:ETF|ETN|FUND)\b", re.IGNORECASE)
_OCC_LIKE = re.compile(r"\d{6}[CP]\d{1,9}\b", re.IGNORECASE)
_DATED_SIDE_LIKE = re.compile(
    r"(?:\d{1,2}/\d{1,2}/\d{2,4}|"
    r"\d{1,2}\s*(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)|"
    r"(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+\d{1,2})"
    r".*\b(?:CALL|PUT|C|P)\b",
    re.IGNORECASE,
)


def option_metadata(*, symbol: str, description: str) -> dict[str, str] | None:
    clean_symbol = "".join(symbol.upper().split())
    parsed = parse_occ_option_symbol(symbol) or parse_occ_option_symbol(clean_symbol)
    if parsed is not None:
        try:
            return _payload(
                underlying=parsed.underlying_symbol,
                expiration=parsed.expiration_date,
                side=parsed.option_type,
                strike=parsed.strike,
            )
        except ValueError:
            pass
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
        try:
            expiration = _date(match.group("date"))
            return _payload(
                underlying=match.group("underlying"),
                expiration=expiration,
                side=_description_side(match),
                strike=_description_strike(match),
            )
        except ValueError:
            pass
    match = _MONTH_DESCRIPTION.search(combined)
    if match is not None:
        try:
            expiration = datetime.strptime(
                f"{match.group('month')} {match.group('day')} {match.group('year')}",
                "%b %d %Y",
            ).date()
            return _payload(
                underlying=match.group("underlying"),
                expiration=expiration,
                side=_description_side(match),
                strike=_description_strike(match),
            )
        except ValueError:
            pass
    match = _DAY_MONTH_DESCRIPTION.search(combined)
    if match is not None:
        try:
            year = match.group("year")
            year_pattern = "%Y" if len(year) == 4 else "%y"
            expiration = datetime.strptime(
                f"{match.group('day')} {match.group('month')} {year}",
                f"%d %b {year_pattern}",
            ).date()
            return _payload(
                underlying=match.group("underlying"),
                expiration=expiration,
                side=_description_side(match),
                strike=_description_strike(match),
            )
        except ValueError:
            pass
    return None


def looks_like_option(*, symbol: str, description: str) -> bool:
    signal = f"{symbol} {description}"
    if any(pattern.search(signal) is not None for pattern in (_OCC_LIKE, _DATED_SIDE_LIKE)):
        return True
    # A fund's name can describe its option strategy without being a contract.
    # Contract-like symbols and dated descriptions still take precedence above.
    if _EQUITY_SYMBOL.fullmatch(symbol.strip()) and _FUND_DESCRIPTION.search(description):
        return False
    return _OPTION_WORD.search(signal) is not None


def contract_multiplier(
    *, explicit: Decimal | None, symbol: str, description: str, is_option: bool
) -> tuple[Decimal | None, str | None]:
    if not is_option:
        return None, None
    if explicit is not None:
        return (explicit, "exported") if explicit > 0 else (None, "invalid_export")
    signal = f"{symbol} {description}".upper()
    if any(token in signal for token in ("ADJUSTED", " ADJ ", "NON-STANDARD", "NONSTANDARD")):
        return None, "unknown_adjusted"
    identity = option_metadata(symbol=symbol, description=description)
    # OCC uses a numeric suffix on the root for adjusted contracts (for
    # example, XYZ1).  Their deliverable is not safely inferable from the
    # symbol, even when the description omits the word "adjusted".
    if identity is not None and any(
        character.isdigit() for character in identity["underlying_symbol"]
    ):
        return None, "unknown_adjusted"
    return Decimal("100"), "assumed_standard"


def _payload(
    *,
    underlying: str,
    expiration: date,
    side: str,
    strike: Decimal,
) -> dict[str, str]:
    root = underlying.upper()
    encoded_strike = strike * Decimal("1000")
    if (
        not 1 <= len(root) <= 6
        or strike <= 0
        or encoded_strike != encoded_strike.to_integral_value()
        or encoded_strike > Decimal("99999999")
    ):
        raise ValueError("option identity cannot be represented as a standard OCC symbol")
    symbol = f"{root:<6}{expiration:%y%m%d}{side[0]}{int(encoded_strike):08d}"
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


def _description_side(match: re.Match[str]) -> str:
    return _side(match.group("side") or match.group("side_first"))


def _description_strike(match: re.Match[str]) -> Decimal:
    return Decimal(match.group("strike") or match.group("strike_after"))
