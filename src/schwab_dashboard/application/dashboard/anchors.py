from __future__ import annotations

import re

NON_ALPHANUMERIC = re.compile(r"[^a-z0-9]+")


def option_contract_anchor(instrument_key: str) -> str:
    """Return a stable, browser-safe anchor for one option instrument."""

    normalized = NON_ALPHANUMERIC.sub("-", instrument_key.strip().lower()).strip("-")
    return f"option-{normalized or 'unknown'}"
