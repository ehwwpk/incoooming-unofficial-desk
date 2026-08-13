from __future__ import annotations

from dataclasses import dataclass

from schwab_dashboard.application.imports.csv_text import HEADER_SCAN_ROWS, CsvText, header_key
from schwab_dashboard.domain.data_source import BrokerKind


@dataclass(frozen=True, slots=True)
class CsvProfile:
    name: str
    broker: BrokerKind
    signatures: tuple[frozenset[str], ...]
    capabilities: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProfileMatch:
    profile: CsvProfile
    header_row: int
    score: int
    confidence: str


PROFILES = (
    CsvProfile(
        "schwab-web",
        BrokerKind.SCHWAB,
        (
            frozenset(("date", "action", "symbol", "description", "quantity", "price", "amount")),
            frozenset(("symbol", "quantity", "price", "marketvalue")),
        ),
        ("positions", "executions", "cash", "dividends", "lifecycle"),
    ),
    CsvProfile(
        "fidelity-web",
        BrokerKind.FIDELITY,
        (
            frozenset(("rundate", "action", "symbol", "description", "amount")),
            frozenset(("accountnamenumber", "symbol", "quantity", "currentvalue")),
        ),
        ("positions", "executions", "cash", "dividends", "lifecycle"),
    ),
    CsvProfile(
        "robinhood-account-activity",
        BrokerKind.ROBINHOOD,
        (frozenset(("activitydate", "processdate", "instrument", "transcode", "amount")),),
        ("executions", "cash", "dividends"),
    ),
    CsvProfile(
        "webull-order-history",
        BrokerKind.WEBULL,
        (frozenset(("filledtime", "symbol", "side", "filled", "avgprice", "status")),),
        ("executions",),
    ),
    CsvProfile(
        "incoooming-canonical",
        BrokerKind.GENERIC,
        (
            frozenset(("account", "date", "action", "symbol", "quantity", "price")),
            frozenset(("account", "symbol", "quantity", "marketvalue")),
        ),
        ("positions", "executions", "cash", "dividends", "lifecycle"),
    ),
)


def select_profile(table: CsvText, requested: BrokerKind) -> ProfileMatch:
    matches: list[ProfileMatch] = []
    for profile in PROFILES:
        for index, row in enumerate(table.rows[:HEADER_SCAN_ROWS], start=1):
            keys = frozenset(header_key(cell) for cell in row if cell)
            score = max((len(keys & signature) for signature in profile.signatures), default=0)
            complete = any(signature <= keys for signature in profile.signatures)
            if complete:
                score += 100
            if score >= 4:
                matches.append(
                    ProfileMatch(
                        profile=profile,
                        header_row=index,
                        score=score + (8 if profile.broker is requested else 0),
                        confidence="high" if complete else "medium",
                    )
                )
    if not matches:
        raise ValueError(
            "No supported positions or activity header was found in the first 30 rows."
        )
    return max(matches, key=lambda item: (item.score, -item.header_row))
