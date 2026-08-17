from datetime import UTC, date, datetime
from decimal import Decimal

from schwab_dashboard.application.dashboard.models import (
    LiveOpenOptionPosition,
    LivePositionBook,
)
from schwab_dashboard.application.dashboard.premium_pace import build_open_premium_pace

D = Decimal


def test_open_premium_pace_includes_calls_and_puts_by_original_term() -> None:
    call = _option(
        symbol="CVX  260220C00200000",
        option_type="CALL",
        contracts=2,
        expires_on=date(2026, 2, 20),
        entry_credit=D("2"),
    )
    put = _option(
        symbol="CVX  260130P00180000",
        option_type="PUT",
        contracts=1,
        expires_on=date(2026, 1, 30),
        entry_credit=D("1"),
    )
    executions = (
        _execution(call.option_symbol, date(2026, 1, 11), quantity="2", price="2"),
        _execution(put.option_symbol, date(2026, 1, 10), quantity="1", price="1"),
    )

    pace = build_open_premium_pace(_book(calls=(call,), puts=(put,)), executions)

    assert pace.opening_credit == D("500")
    assert pace.daily_pace == D("15")
    assert pace.weighted_term_days == D("33.33333333333333333333333333")
    assert pace.timed_contracts == 3
    assert pace.total_contracts == 3
    assert pace.is_complete


def test_open_premium_pace_times_only_the_fifo_lot_still_open() -> None:
    call = _option(
        symbol="CVX  260220C00200000",
        option_type="CALL",
        contracts=1,
        expires_on=date(2026, 2, 20),
        entry_credit=D("2"),
    )
    executions = (
        _execution(call.option_symbol, date(2026, 1, 11), quantity="2", price="2"),
        _execution(
            call.option_symbol,
            date(2026, 1, 20),
            quantity="1",
            price="0.5",
            side="buy",
            effect="closing",
        ),
    )

    pace = build_open_premium_pace(_book(calls=(call,)), executions)

    assert pace.opening_credit == D("200")
    assert pace.daily_pace == D("5")
    assert pace.weighted_term_days == D("40")
    assert pace.timed_contracts == 1


def test_open_premium_pace_withholds_daily_number_when_history_does_not_reconcile() -> None:
    call = _option(
        symbol="CVX  260220C00200000",
        option_type="CALL",
        contracts=1,
        expires_on=date(2026, 2, 20),
        entry_credit=D("2"),
    )

    pace = build_open_premium_pace(_book(calls=(call,)), ())

    assert pace.opening_credit == D("200")
    assert pace.daily_pace is None
    assert pace.weighted_term_days is None
    assert pace.timed_contracts == 0
    assert pace.total_contracts == 1
    assert not pace.is_complete


def test_open_premium_pace_counts_zero_dte_as_one_earning_session() -> None:
    put = _option(
        symbol="CVX  260130P00180000",
        option_type="PUT",
        contracts=3,
        expires_on=date(2026, 1, 30),
        entry_credit=D("0.10"),
    )
    executions = (
        _execution(put.option_symbol, date(2026, 1, 30), quantity="3", price="0.10"),
    )

    pace = build_open_premium_pace(_book(puts=(put,)), executions)

    assert pace.opening_credit == D("30")
    assert pace.daily_pace == D("30")
    assert pace.weighted_term_days == D("1")
    assert pace.is_complete


def _option(
    *,
    symbol: str,
    option_type: str,
    contracts: int,
    expires_on: date,
    entry_credit: Decimal,
) -> LiveOpenOptionPosition:
    return LiveOpenOptionPosition(
        account_mask="...1234",
        option_symbol=symbol,
        underlying_symbol="CVX",
        contracts=contracts,
        expires_on=expires_on,
        days_to_expiration=10,
        strike=D("200"),
        entry_credit_per_share=entry_credit,
        estimated_mark_per_share=D("1"),
        market_value=None,
        open_profit_loss=None,
        day_profit_loss=None,
        underlying_price=D("190"),
        strike_distance_per_share=D("10"),
        strike_distance_percent=D("5"),
        option_type=option_type,
    )


def _book(
    *,
    calls: tuple[LiveOpenOptionPosition, ...] = (),
    puts: tuple[LiveOpenOptionPosition, ...] = (),
) -> LivePositionBook:
    return LivePositionBook(
        underlyings=(),
        calls=calls,
        total_shares=0,
        contract_capacity=0,
        open_call_positions=len(calls),
        open_call_contracts=sum(item.contracts for item in calls),
        covered_contracts=0,
        uncovered_contracts=0,
        coverage_percent=D("0"),
        open_mark_profit_loss=D("0"),
        puts=puts,
        open_put_positions=len(puts),
        open_put_contracts=sum(item.contracts for item in puts),
    )


def _execution(
    symbol: str,
    occurred_on: date,
    *,
    quantity: str,
    price: str,
    side: str = "sell",
    effect: str = "opening",
) -> dict[str, object]:
    return {
        "account_mask": "...1234",
        "symbol": symbol,
        "asset_type": "option",
        "occurred_at": datetime(
            occurred_on.year,
            occurred_on.month,
            occurred_on.day,
            16,
            tzinfo=UTC,
        ),
        "quantity": D(quantity),
        "price": D(price),
        "side": side,
        "position_effect": effect,
    }
