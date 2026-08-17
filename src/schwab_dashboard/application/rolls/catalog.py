from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from schwab_dashboard.domain.instruments import OptionSide
from schwab_dashboard.domain.opportunity import RadarMode

if TYPE_CHECKING:
    from schwab_dashboard.application.dashboard.models import DashboardSnapshot


@dataclass(frozen=True, slots=True)
class RollSourceChoice:
    """One currently open short option that Radar can review independently."""

    symbol: str
    option_symbol: str
    option_side: OptionSide
    expires_on: date
    days_to_expiration: int
    strike: Decimal
    contracts: int
    strike_distance_percent: Decimal | None

    @property
    def mode(self) -> RadarMode:
        return (
            RadarMode.COVERED_CALL
            if self.option_side is OptionSide.CALL
            else RadarMode.CASH_SECURED_PUT
        )

    @property
    def side_code(self) -> str:
        return "C" if self.option_side is OptionSide.CALL else "P"


def build_roll_source_catalog(snapshot: DashboardSnapshot) -> tuple[RollSourceChoice, ...]:
    """List every short option that can still be closed or rolled."""

    choices: list[RollSourceChoice] = []
    for underlying in snapshot.underlyings:
        choices.extend(
            RollSourceChoice(
                symbol=underlying.symbol,
                option_symbol=call.record_id,
                option_side=OptionSide.CALL,
                expires_on=call.expires_on,
                days_to_expiration=call.days_to_expiration,
                strike=call.strike,
                contracts=call.contracts,
                strike_distance_percent=call.strike_distance_percent,
            )
            for call in underlying.open_call_clocks
            if call.can_close_or_roll
        )
    if snapshot.live_position_book is not None:
        choices.extend(
            RollSourceChoice(
                symbol=put.underlying_symbol,
                option_symbol=put.option_symbol,
                option_side=OptionSide.PUT,
                expires_on=put.expires_on,
                days_to_expiration=put.days_to_expiration,
                strike=put.strike,
                contracts=put.contracts,
                strike_distance_percent=put.strike_distance_percent,
            )
            for put in snapshot.live_position_book.puts
            if put.can_close_or_roll
        )
    return tuple(
        sorted(
            choices,
            key=lambda choice: (
                choice.days_to_expiration,
                abs(choice.strike_distance_percent or Decimal("999")),
                choice.symbol,
                choice.option_side.value,
                choice.strike,
            ),
        )
    )
