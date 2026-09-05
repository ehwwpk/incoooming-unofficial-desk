"""Use production inventory/risk math with complete, explicitly fictional inputs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, date, datetime, time
from decimal import Decimal

from schwab_dashboard.application.dashboard.covered_calls import CallSaleRecord
from schwab_dashboard.application.dashboard.live_positions import build_live_position_book
from schwab_dashboard.application.dashboard.models import (
    LiveOpenOptionPosition,
    LivePositionBook,
    PositionSummary,
)
from schwab_dashboard.application.rolls.models import RollQuote
from schwab_dashboard.infrastructure.demo.fixtures.daily_prices import DAILY_CLOSES
from schwab_dashboard.infrastructure.demo.fixtures.open_call_metrics import OPEN_CALL_METRICS
from schwab_dashboard.infrastructure.demo.fixtures.roll_quotes import (
    PUT_ROLL_QUOTE_CANDIDATES,
    ROLL_QUOTE_CANDIDATES,
)
from schwab_dashboard.infrastructure.demo.fixtures.short_puts import (
    PUT_FIXTURES,
    build_put_executions,
)

D = Decimal


def build_demo_opening_executions(
    records: Sequence[CallSaleRecord],
) -> tuple[dict[str, object], ...]:
    """Only surviving lots, for inventory terms and pace; not a cash ledger."""

    return (
        *(
            {
                "external_key": item.record_id,
                "order_external_key": item.record_id,
                "account_mask": "...4831",
                "occurred_at": datetime.combine(item.sold_on, time(16), tzinfo=UTC),
                "side": "sell",
                "position_effect": "opening",
                "asset_type": "option",
                "symbol": f"{item.symbol} {item.expires_on:%y%m%d}C{int(item.strike * 1000):08d}",
                "underlying_symbol": item.symbol,
                "option_side": "call",
                "strike": item.strike,
                "expiration_date": item.expires_on,
                "quantity": D(item.contracts),
                "price": item.premium_per_share,
                "contract_multiplier": D("100"),
                "is_non_standard": False,
                "gross_amount": item.gross_premium,
                "net_cash": item.gross_premium,
                "fees": D("0"),
            }
            for item in records
            if item.outcome == "Open"
        ),
        *build_put_executions(),
    )


def build_demo_position_book(
    positions: Sequence[PositionSummary],
    records: Sequence[CallSaleRecord],
    *,
    as_of: date | datetime,
) -> LivePositionBook:
    observed_at = (
        as_of if isinstance(as_of, datetime) else datetime.combine(as_of, time(21, 15), tzinfo=UTC)
    )
    put_metrics = {(item.symbol, item.expires_on, item.strike): item for item in PUT_FIXTURES}
    option_market: list[dict[str, object]] = []
    for position in positions:
        if position.asset_type != "OPTION":
            continue
        assert position.underlying_symbol is not None
        assert position.expiration_date is not None
        assert position.strike is not None
        key = (position.underlying_symbol, position.expiration_date, position.strike)
        metric = put_metrics[key] if position.option_type == "PUT" else OPEN_CALL_METRICS[key]
        option_market.append(
            {
                "symbol": position.symbol,
                "bid": metric.bid_per_share,
                "mark": metric.mark_per_share,
                "ask": metric.ask_per_share,
                "implied_volatility": metric.implied_volatility_percent,
                "delta": metric.delta,
                "gamma": metric.gamma,
                "theta": metric.theta_per_share,
                "vega": metric.vega,
                "volume": getattr(metric, "volume", 175),
                "open_interest": getattr(metric, "open_interest", 1200),
                "observed_at": observed_at,
                # Completeness measures available model inputs, not their provenance.
                # The adapter and every roll quote explicitly identify demo simulation.
                "quote_quality": "complete",
            }
        )
    book = build_live_position_book(
        positions,
        as_of=observed_at,
        evaluated_at=observed_at,
        option_market=option_market,
        underlying_market=tuple(
            {
                "symbol": position.symbol,
                "mark": position.mark,
                "previous_close": D(DAILY_CLOSES[position.symbol][-2][1]),
                "observed_at": observed_at,
                "quote_quality": "complete",
            }
            for position in positions
            if position.asset_type == "EQUITY"
        ),
        daily_bars=tuple(
            {
                "symbol": symbol,
                "trade_date": date(2026, int(day[:2]), int(day[3:])),
                "close": D(close),
            }
            for symbol, rows in DAILY_CLOSES.items()
            for day, close in rows
        ),
        executions=build_demo_opening_executions(records),
    )

    def with_simulated_rolls(option: LiveOpenOptionPosition) -> LiveOpenOptionPosition:
        grid = PUT_ROLL_QUOTE_CANDIDATES if option.option_type == "PUT" else ROLL_QUOTE_CANDIDATES
        quotes = grid.get((option.underlying_symbol, option.expires_on, option.strike), ())
        return replace(
            option,
            roll_quote_candidates=tuple(
                RollQuote(
                    option_symbol=quote.option_symbol,
                    expires_on=quote.expires_on,
                    strike=quote.strike,
                    sell_bid_per_share=quote.sell_bid_per_share,
                    quote_source="SIMULATED BID",
                    spread_percent=D("5"),
                    open_interest=1200,
                    volume=175,
                    quote_observed_at=observed_at,
                )
                for quote in quotes
            ),
        )

    calls = tuple(with_simulated_rolls(item) for item in book.calls)
    puts = tuple(with_simulated_rolls(item) for item in book.puts)
    return replace(
        book,
        calls=calls,
        puts=puts,
        underlyings=tuple(
            replace(
                item,
                calls=tuple(call for call in calls if call.underlying_symbol == item.symbol),
                puts=tuple(put for put in puts if put.underlying_symbol == item.symbol),
            )
            for item in book.underlyings
        ),
    )
