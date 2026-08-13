from __future__ import annotations

from decimal import Decimal

from schwab_dashboard.application.alerts.models import RollScenario
from schwab_dashboard.application.dashboard.covered_calls import OpenCallClock

D = Decimal
ZERO = D("0")
HUNDRED = D("100")
DEFAULT_NEUTRAL_BAND = D("0.10")


def build_neutral_roll_scenarios(
    call: OpenCallClock,
    *,
    current_price: Decimal,
    neutral_band_per_share: Decimal = DEFAULT_NEUTRAL_BAND,
    limit: int = 2,
) -> tuple[RollScenario, ...]:
    """Compare higher/later calls using conservative two-sided quote math.

    The current short call is bought at its ask and the replacement call is sold
    at its bid. Only near-flat candidates are retained. Commissions, fees, taxes,
    slippage, and later quote movement are deliberately excluded.
    """

    candidates: list[RollScenario] = []
    contract_shares = D(call.contracts * 100)
    for quote in call.roll_quote_candidates:
        if quote.strike <= call.strike or quote.expires_on <= call.expires_on:
            continue
        net_per_share = quote.sell_bid_per_share - call.close_ask_per_share
        if abs(net_per_share) > neutral_band_per_share:
            continue
        strike_lift = quote.strike - call.strike
        buffer_percent = (
            (quote.strike - current_price) / current_price * HUNDRED
            if current_price > ZERO
            else ZERO
        )
        candidates.append(
            RollScenario(
                source_option_symbol=call.record_id,
                source_expiration=call.expires_on,
                source_strike=call.strike,
                source_contracts=call.contracts,
                target_expiration=quote.expires_on,
                target_strike=quote.strike,
                strike_lift_per_share=strike_lift,
                added_days=(quote.expires_on - call.expires_on).days,
                net_roll_per_share=net_per_share,
                net_roll_cash=net_per_share * contract_shares,
                assignment_room_gain=strike_lift * contract_shares,
                target_buffer_percent=buffer_percent.quantize(D("0.1")),
                quote_source=quote.quote_source,
            )
        )

    candidates.sort(
        key=lambda scenario: (
            scenario.added_days,
            abs(scenario.net_roll_per_share),
            -scenario.strike_lift_per_share,
        )
    )
    return tuple(candidates[:limit])
