from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from schwab_dashboard.application.dashboard.models import (
    CampaignSummary,
    LiveOpenOptionPosition,
)
from schwab_dashboard.application.dashboard.option_clock_math import (
    put_decay_stage,
    put_effective_entry_per_share,
    put_intrinsic_value,
    short_option_term,
    short_option_value_vs_credit,
)
from schwab_dashboard.application.expiration import OptionExpirationAssessment
from schwab_dashboard.application.market_time import OptionSessionState
from schwab_dashboard.application.risk.price_time import PriceTimeRead

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class OpenPutClock:
    """Desk presentation of one open short put, using Open Options clock math."""

    option_symbol: str
    campaign_id: str
    campaign_label: str
    contracts: int
    sold_on: date | None
    expires_on: date
    original_days_to_expiration: int | None
    days_to_expiration: int
    strike: Decimal
    strike_distance_per_share: Decimal | None
    strike_distance_percent: Decimal | None
    entry_credit_per_share: Decimal
    entry_credit: Decimal
    effective_entry_per_share: Decimal | None
    mark_per_share: Decimal
    current_option_value: Decimal
    open_profit_loss: Decimal
    elapsed_time_percent: Decimal | None
    time_remaining_percent: Decimal | None
    option_value_vs_credit_percent: Decimal
    option_value_track_percent: Decimal
    option_value_overrun_percent: Decimal
    credit_capture_percent: Decimal
    intrinsic_value: Decimal
    remaining_extrinsic_value: Decimal
    decay_stage: str
    short_theta_per_day: Decimal
    implied_volatility_percent: Decimal | None
    price_time_read: PriceTimeRead
    quote_observed_at: datetime | None = None
    quote_observed_on: date | None = None
    quote_status: str = "UNAVAILABLE"
    session_state: OptionSessionState = OptionSessionState.ACTIVE
    session_label: str = "OPEN"
    can_close_or_roll: bool = True
    expiration_assessment: OptionExpirationAssessment | None = None


def build_open_put_clocks(
    puts: Sequence[LiveOpenOptionPosition],
    *,
    campaigns: Sequence[CampaignSummary] = (),
) -> tuple[OpenPutClock, ...]:
    return tuple(_clock(put, campaigns=campaigns) for put in puts)


def _clock(
    put: LiveOpenOptionPosition,
    *,
    campaigns: Sequence[CampaignSummary],
) -> OpenPutClock:
    multiplier = abs(put.contract_multiplier or Decimal("100"))
    contracts = Decimal(put.contracts)
    entry_available = put.entry_credit_per_share is not None
    entry_credit_per_share = abs(put.entry_credit_per_share or ZERO)
    entry_credit = entry_credit_per_share * multiplier * contracts
    mark_per_share = abs(put.estimated_mark_per_share or ZERO)
    current_value = abs(
        put.market_value
        if put.market_value is not None
        else mark_per_share * multiplier * contracts
    )
    term = short_option_term(
        opened_on=put.opened_on,
        expires_on=put.expires_on,
        original_days_to_expiration=put.original_days_to_expiration,
        days_to_expiration=put.days_to_expiration,
    )
    value = short_option_value_vs_credit(
        entry_credit=entry_credit,
        current_liability=current_value,
    )
    intrinsic_value = put_intrinsic_value(
        strike=put.strike,
        underlying_price=put.underlying_price,
        multiplier=multiplier,
        contracts=put.contracts,
    )
    short_theta = (
        -(put.theta_per_share or ZERO) * multiplier * contracts if put.can_close_or_roll else ZERO
    )
    campaign_id, campaign_label = _resolve_put_campaign(put, campaigns)
    return OpenPutClock(
        option_symbol=put.option_symbol,
        campaign_id=campaign_id,
        campaign_label=campaign_label,
        contracts=put.contracts,
        sold_on=put.opened_on,
        expires_on=put.expires_on,
        original_days_to_expiration=put.original_days_to_expiration,
        days_to_expiration=put.days_to_expiration,
        strike=put.strike,
        strike_distance_per_share=put.strike_distance_per_share,
        strike_distance_percent=put.strike_distance_percent,
        entry_credit_per_share=entry_credit_per_share,
        entry_credit=entry_credit,
        effective_entry_per_share=put_effective_entry_per_share(
            strike=put.strike,
            entry_credit_per_share=put.entry_credit_per_share if entry_available else None,
        ),
        mark_per_share=mark_per_share,
        current_option_value=current_value,
        open_profit_loss=put.open_profit_loss or ZERO,
        elapsed_time_percent=term.elapsed_time_percent,
        time_remaining_percent=term.time_remaining_percent,
        option_value_vs_credit_percent=value.option_value_vs_credit_percent,
        option_value_track_percent=value.option_value_track_percent,
        option_value_overrun_percent=value.option_value_overrun_percent,
        credit_capture_percent=value.credit_capture_percent,
        intrinsic_value=intrinsic_value,
        remaining_extrinsic_value=max(ZERO, current_value - intrinsic_value),
        decay_stage=put_decay_stage(
            put.days_to_expiration,
            term.elapsed_time_percent,
            session_label=put.session_label,
            can_close_or_roll=put.can_close_or_roll,
        ),
        short_theta_per_day=short_theta,
        implied_volatility_percent=put.implied_volatility_percent,
        price_time_read=put.price_time_read,
        quote_observed_at=put.quote_observed_at,
        quote_observed_on=(
            put.quote_observed_at.date() if put.quote_observed_at is not None else None
        ),
        quote_status=(put.quote_quality or "unavailable").upper(),
        session_state=put.session_state,
        session_label=put.session_label,
        can_close_or_roll=put.can_close_or_roll,
        expiration_assessment=put.expiration_assessment,
    )


def _resolve_put_campaign(
    put: LiveOpenOptionPosition,
    campaigns: Sequence[CampaignSummary],
) -> tuple[str, str]:
    """Attach a chip only when exactly one open put campaign matches this line."""

    matches = [
        campaign
        for campaign in campaigns
        if campaign.symbol == put.underlying_symbol
        and str(campaign.option_side).lower() == "put"
        and campaign.status == "OPEN"
        and campaign.expires_on == put.expires_on
        and campaign.current_strike == put.strike
    ]
    if len(matches) != 1:
        return "", ""
    return matches[0].campaign_id, matches[0].campaign_label
