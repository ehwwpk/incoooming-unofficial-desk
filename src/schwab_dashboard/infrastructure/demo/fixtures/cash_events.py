from datetime import date
from decimal import Decimal

from schwab_dashboard.application.dashboard.cashflows import CashEvent

D = Decimal


DIVIDEND_CASH_EVENTS = (
    CashEvent(
        event_id="cvx-div-2026-q2",
        occurred_on=date(2026, 6, 10),
        symbol="CVX",
        event_type="DIVIDEND",
        amount=D("1246.00"),
        contracts=0,
    ),
)


def build_dividend_cash_events() -> tuple[CashEvent, ...]:
    return DIVIDEND_CASH_EVENTS
