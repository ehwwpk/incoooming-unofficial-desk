from datetime import UTC, date, datetime
from decimal import Decimal

from schwab_dashboard.application.dashboard.models import (
    CampaignSummary,
    LiveOpenOptionPosition,
)
from schwab_dashboard.application.dashboard.open_put_clocks import build_open_put_clocks
from schwab_dashboard.application.workspaces.projections import _open_put_row

D = Decimal


def _put(**overrides: object) -> LiveOpenOptionPosition:
    values: dict[str, object] = {
        "account_mask": "...1234",
        "option_symbol": "KTOS  260821P00060000",
        "underlying_symbol": "KTOS",
        "contracts": 1,
        "expires_on": date(2026, 8, 21),
        "days_to_expiration": 3,
        "strike": D("60"),
        "entry_credit_per_share": D("1.50"),
        "estimated_mark_per_share": D("0.40"),
        "market_value": D("-40"),
        "open_profit_loss": D("110"),
        "day_profit_loss": D("10"),
        "underlying_price": D("68"),
        "strike_distance_per_share": D("8"),
        "strike_distance_percent": D("11.76"),
        "theta_per_share": D("-0.05"),
        "implied_volatility_percent": D("48"),
        "option_type": "PUT",
        "opened_on": date(2026, 7, 10),
        "original_days_to_expiration": 42,
    }
    values.update(overrides)
    return LiveOpenOptionPosition(**values)  # type: ignore[arg-type]


def _campaign(**overrides: object) -> CampaignSummary:
    values: dict[str, object] = {
        "campaign_id": "put-ktos-1",
        "symbol": "KTOS",
        "intent_label": "SHORT PUT",
        "status": "OPEN",
        "opened_on": date(2026, 7, 10),
        "expires_on": date(2026, 8, 21),
        "days_to_expiration": 3,
        "legs": ("P1",),
        "gross_opening_credit": D("150"),
        "closing_debits": D("0"),
        "fees": D("0"),
        "net_cash_to_date": D("150"),
        "realized_cash": D("0"),
        "open_credit": D("150"),
        "estimated_close_value": D("40"),
        "open_mark_profit_loss": D("110"),
        "initial_strike": D("60"),
        "current_strike": D("60"),
        "strike_change": D("0"),
        "days_extended": 0,
        "called_away_shares": 0,
        "effective_exit_price": None,
        "collateral": D("6000"),
        "cash_on_capital_percent": D("2.5"),
        "progress_percent": 40,
        "campaign_label": "P1",
        "option_side": "put",
    }
    values.update(overrides)
    return CampaignSummary(**values)  # type: ignore[arg-type]


def test_open_put_clock_matches_open_book_row_math() -> None:
    put = _put()
    clock = build_open_put_clocks((put,))[0]
    row = _open_put_row(put)

    assert clock.elapsed_time_percent == row.elapsed_time_percent
    assert clock.time_remaining_percent == row.time_remaining_percent
    assert clock.option_value_vs_credit_percent == row.option_value_vs_credit_percent
    assert clock.current_option_value == row.current_liability
    assert clock.effective_entry_per_share == row.effective_entry_per_share == D("58.50")
    assert clock.intrinsic_value == row.intrinsic_value == D("0")
    assert clock.decay_stage == row.decay_stage == "EXPIRING SOON"
    assert clock.short_theta_per_day == row.theta_estimate_per_day == D("5.00")
    assert clock.sold_on == date(2026, 7, 10)


def test_open_put_clock_does_not_guess_term_without_a_sale_date() -> None:
    clock = build_open_put_clocks(
        (_put(opened_on=None, original_days_to_expiration=None, days_to_expiration=21),)
    )[0]

    assert clock.elapsed_time_percent is None
    assert clock.time_remaining_percent is None
    assert clock.decay_stage == "OPEN TERM"


def test_open_put_clock_uses_the_sale_date_when_original_span_is_missing() -> None:
    clock = build_open_put_clocks(
        (
            _put(
                original_days_to_expiration=None,
                opened_on=date(2026, 7, 10),
                expires_on=date(2026, 8, 21),
                days_to_expiration=21,
            ),
        )
    )[0]

    assert clock.elapsed_time_percent == D("50")
    assert clock.time_remaining_percent == D("50")
    assert clock.decay_stage == "MID CYCLE"
    assert clock.sold_on == date(2026, 7, 10)


def test_itm_put_intrinsic_uses_strike_minus_spot() -> None:
    clock = build_open_put_clocks(
        (
            _put(
                underlying_price=D("55"),
                strike=D("60"),
                contracts=2,
                market_value=D("-1200"),
            ),
        )
    )[0]

    assert clock.intrinsic_value == D("1000")
    assert clock.remaining_extrinsic_value == D("200")


def test_put_clock_attaches_a_campaign_chip_only_for_a_single_open_match() -> None:
    put = _put()
    matched = build_open_put_clocks((put,), campaigns=(_campaign(),))[0]
    ambiguous = build_open_put_clocks(
        (put,),
        campaigns=(_campaign(), _campaign(campaign_id="put-ktos-2", campaign_label="P2")),
    )[0]
    closed = build_open_put_clocks((put,), campaigns=(_campaign(status="CLOSED"),))[0]
    call_side = build_open_put_clocks((put,), campaigns=(_campaign(option_side="call"),))[0]

    assert matched.campaign_id == "put-ktos-1"
    assert matched.campaign_label == "P1"
    assert ambiguous.campaign_id == ""
    assert ambiguous.campaign_label == ""
    assert closed.campaign_label == ""
    assert call_side.campaign_label == ""


def test_open_put_clock_threads_quote_age() -> None:
    observed = datetime(2026, 8, 6, 20, tzinfo=UTC)
    clock = build_open_put_clocks(
        (_put(quote_observed_at=observed, quote_quality="complete"),)
    )[0]
    assert clock.quote_observed_on == date(2026, 8, 6)
    assert clock.quote_status == "COMPLETE"
    assert clock.quote_observed_at == observed
