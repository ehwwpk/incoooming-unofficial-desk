from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from schwab_dashboard.application.dashboard.covered_calls import RollQuoteCandidate

D = Decimal


def _quotes(*rows: tuple[date, str, str, str]) -> tuple[RollQuoteCandidate, ...]:
    return tuple(
        RollQuoteCandidate(
            option_symbol=option_symbol,
            expires_on=expires_on,
            strike=D(strike),
            sell_bid_per_share=D(bid),
            quote_source="SIMULATED BID",
        )
        for expires_on, strike, bid, option_symbol in rows
    )


def _weekly_grid(
    start: date,
    *,
    strikes: tuple[str, str, str],
    bids: tuple[tuple[str, str, str], tuple[str, str, str], tuple[str, str, str]],
    symbols: tuple[tuple[str, ...], ...] | None = None,
) -> tuple[RollQuoteCandidate, ...]:
    rows: list[tuple[date, str, str, str]] = []
    for week, (week_bids, week_symbols) in enumerate(
        zip(
            bids,
            symbols
            or tuple(
                tuple(f"{expiry.isoformat()}-{strike}" for strike in strikes)
                for expiry in (start + timedelta(days=7 * offset) for offset in range(3))
            ),
            strict=True,
        )
    ):
        expiry = start + timedelta(days=7 * week)
        for strike, bid, option_symbol in zip(strikes, week_bids, week_symbols, strict=True):
            rows.append((expiry, strike, bid, option_symbol))
    return _quotes(*rows)


ROLL_QUOTE_CANDIDATES = {
    ("CVX", date(2026, 8, 14), D("195")): _weekly_grid(
        date(2026, 8, 21),
        strikes=("200", "205", "210"),
        bids=(("2.55", "1.00", "0.80"), ("2.35", "1.85", "1.15"), ("2.20", "1.65", "1.05")),
        symbols=(
            ("CVX-2026-08-21-200", "cvx-0731-205", "CVX-2026-08-21-210"),
            ("CVX-2026-08-28-200", "CVX-2026-08-28-205", "CVX-2026-08-28-210"),
            ("CVX-2026-09-04-200", "CVX-2026-09-04-205", "CVX-2026-09-04-210"),
        ),
    ),
    ("CVX", date(2026, 8, 21), D("205")): _weekly_grid(
        date(2026, 8, 28),
        strikes=("210", "215", "220"),
        bids=(("1.15", "0.85", "0.55"), ("1.05", "0.75", "0.45"), ("0.95", "0.65", "0.35")),
    ),
    ("CVX", date(2026, 9, 18), D("215")): _weekly_grid(
        date(2026, 9, 25),
        strikes=("220", "225", "230"),
        bids=(("1.25", "0.90", "0.60"), ("1.15", "0.80", "0.50"), ("1.05", "0.70", "0.40")),
    ),
    ("KTOS", date(2026, 8, 28), D("75")): _weekly_grid(
        date(2026, 9, 4),
        strikes=("80", "85", "90"),
        bids=(("0.75", "0.50", "0.30"), ("0.68", "0.42", "0.24"), ("0.60", "0.35", "0.18")),
    ),
    ("KTOS", date(2026, 9, 25), D("90")): _weekly_grid(
        date(2026, 10, 2),
        strikes=("95", "100", "105"),
        bids=(("0.65", "0.45", "0.28"), ("0.58", "0.38", "0.22"), ("0.50", "0.30", "0.16")),
    ),
    ("URNM", date(2026, 9, 18), D("67.5")): _weekly_grid(
        date(2026, 9, 25),
        strikes=("70", "72.5", "75"),
        bids=(("0.92", "0.70", "0.48"), ("0.84", "0.62", "0.40"), ("0.76", "0.54", "0.32")),
    ),
}


# Fictional later puts: same-strike extensions and lower purchase obligations.
# At a fixed strike, longer terms carry more premium; lower strikes cost less.
PUT_ROLL_QUOTE_CANDIDATES = {
    ("KTOS", date(2026, 8, 28), D("60")): _weekly_grid(
        date(2026, 9, 4),
        strikes=("60", "59", "57.5"),
        bids=(("3.40", "2.90", "2.35"), ("3.70", "3.20", "2.60"), ("4.00", "3.50", "2.85")),
        symbols=tuple(
            tuple(
                f"KTOS {expiry:%y%m%d}P{int(D(strike) * 1000):08d}"
                for strike in ("60", "59", "57.5")
            )
            for expiry in (date(2026, 9, 4), date(2026, 9, 11), date(2026, 9, 18))
        ),
    ),
    ("URNM", date(2026, 8, 21), D("55")): _weekly_grid(
        date(2026, 8, 28),
        strikes=("55", "54", "52.5"),
        bids=(("2.60", "2.05", "1.35"), ("2.85", "2.30", "1.60"), ("3.10", "2.55", "1.85")),
        symbols=tuple(
            tuple(
                f"URNM {expiry:%y%m%d}P{int(D(strike) * 1000):08d}"
                for strike in ("55", "54", "52.5")
            )
            for expiry in (date(2026, 8, 28), date(2026, 9, 4), date(2026, 9, 11))
        ),
    ),
}
