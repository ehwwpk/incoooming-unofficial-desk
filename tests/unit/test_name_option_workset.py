from dataclasses import replace
from datetime import date
from decimal import Decimal

from schwab_dashboard.application.dashboard.live_positions import build_live_position_book
from schwab_dashboard.application.dashboard.models import LiveOpenOptionPosition, PositionSummary
from schwab_dashboard.application.dashboard.open_put_clocks import build_open_put_clocks
from schwab_dashboard.application.dashboard.overview import (
    NAME_OPTION_PRIORITY,
    build_desk_overview,
    ordered_name_options,
)
from schwab_dashboard.infrastructure.demo.dashboard import DemoDashboardReader
from schwab_dashboard.web.rendering import templates

D = Decimal


def _put_clock(
    *,
    expires_on: date,
    strike: Decimal,
    distance_percent: Decimal | None,
    days_to_expiration: int = 10,
    option_symbol: str = "KTOS  260821P00060000",
):
    put = LiveOpenOptionPosition(
        account_mask="...1234",
        option_symbol=option_symbol,
        underlying_symbol="KTOS",
        contracts=1,
        expires_on=expires_on,
        days_to_expiration=days_to_expiration,
        strike=strike,
        entry_credit_per_share=D("1.20"),
        estimated_mark_per_share=D("0.50"),
        market_value=D("-50"),
        open_profit_loss=D("70"),
        day_profit_loss=D("0"),
        underlying_price=D("68"),
        strike_distance_per_share=None if distance_percent is None else D("8"),
        strike_distance_percent=distance_percent,
        option_type="PUT",
        opened_on=date(2026, 7, 1),
        original_days_to_expiration=50,
    )
    return build_open_put_clocks((put,))[0]


def test_name_options_sort_by_expiry_then_proximity_with_put_strikes_descending() -> None:
    snapshot = DemoDashboardReader().execute()
    ktos = next(item for item in snapshot.underlyings if item.symbol == "KTOS")
    first, second = ktos.open_call_clocks[0], ktos.open_call_clocks[1]
    calls = (
        replace(
            first,
            expires_on=date(2026, 8, 21),
            strike=D("85"),
            strike_distance_percent=D("25"),
        ),
        replace(
            second,
            expires_on=date(2026, 8, 21),
            strike=D("90"),
            strike_distance_percent=D("32"),
        ),
    )
    puts = (
        _put_clock(
            expires_on=date(2026, 8, 21),
            strike=D("56"),
            distance_percent=D("18"),
            option_symbol="KTOS  260821P00056000",
        ),
        _put_clock(
            expires_on=date(2026, 8, 21),
            strike=D("60"),
            distance_percent=D("12"),
            option_symbol="KTOS  260821P00060000",
        ),
        _put_clock(
            expires_on=date(2026, 8, 28),
            strike=D("56"),
            distance_percent=D("18"),
            option_symbol="KTOS  260828P00056000",
        ),
    )

    ordered = ordered_name_options(calls, puts)

    assert [item.side for item in ordered] == ["put", "put", "call", "call", "put"]
    assert ordered[0].strike == D("60")
    assert ordered[1].strike == D("56")
    assert ordered[2].strike == D("85")
    assert ordered[3].strike == D("90")
    assert len(ordered[:NAME_OPTION_PRIORITY]) == 3
    assert ordered[3].side == "call"


def test_name_options_send_missing_put_distance_last_on_the_same_expiry() -> None:
    snapshot = DemoDashboardReader().execute()
    call = replace(
        snapshot.underlyings[0].open_call_clocks[0],
        expires_on=date(2026, 8, 21),
        strike_distance_percent=D("20"),
    )
    known = _put_clock(
        expires_on=date(2026, 8, 21),
        strike=D("60"),
        distance_percent=D("10"),
    )
    missing = _put_clock(
        expires_on=date(2026, 8, 21),
        strike=D("50"),
        distance_percent=None,
        option_symbol="KTOS  260821P00050000",
    )

    ordered = ordered_name_options((call,), (known, missing))

    assert [item.side for item in ordered] == ["put", "call", "put"]
    assert ordered[0].strike == D("60")
    assert ordered[2].strike_distance_percent is None


def test_name_options_prefer_the_call_when_expiry_and_proximity_tie() -> None:
    snapshot = DemoDashboardReader().execute()
    call = replace(
        snapshot.underlyings[0].open_call_clocks[0],
        expires_on=date(2026, 8, 21),
        strike_distance_percent=D("10"),
    )
    put = _put_clock(
        expires_on=date(2026, 8, 21),
        strike=D("60"),
        distance_percent=D("10"),
    )

    ordered = ordered_name_options((call,), (put,))

    assert [item.side for item in ordered] == ["call", "put"]


def test_desk_row_puts_nearer_expiries_in_the_working_set() -> None:
    snapshot = DemoDashboardReader().execute()
    ktos = next(item for item in snapshot.underlyings if item.symbol == "KTOS")
    early_put = PositionSummary(
        account_mask="...1234",
        symbol="KTOS  260821P00060000",
        description="KTOS AUG 21 2026 60 Put",
        asset_type="OPTION",
        quantity=D("-1"),
        average_price=D("1.50"),
        mark=D("0.40"),
        market_value=D("-40"),
        day_profit_loss=D("10"),
        day_profit_loss_percent=None,
        strategy="Short put",
        underlying_symbol="KTOS",
        option_type="PUT",
        expiration_date=date(2026, 8, 21),
        strike=D("60"),
        open_profit_loss=D("110"),
    )
    later_put = replace(
        early_put,
        symbol="KTOS  260918P00050000",
        expiration_date=date(2026, 9, 18),
        strike=D("50"),
    )
    snapshot_with_puts = replace(
        snapshot,
        live_position_book=build_live_position_book(
            (*snapshot.positions, early_put, later_put),
            as_of=snapshot.as_of.date(),
        ),
    )
    row = next(
        item
        for item in build_desk_overview(snapshot_with_puts).position_rows
        if item.underlying.symbol == "KTOS"
    )

    assert len(ktos.open_call_clocks) == 2
    assert [option.side for option in row.priority_options] == ["put", "call", "put"]
    assert row.priority_options[0].put is not None
    assert row.priority_options[0].put.strike == D("60")
    assert row.priority_options[2].put is not None
    assert row.priority_options[2].put.strike == D("50")
    assert len(row.overflow_options) == 1
    assert row.overflow_options[0].side == "call"
    assert row.overflow_put_count == 0
    assert row.overflow_call_count == 1
    assert row.priority_status_caption == "NEAREST 3 BY EXPIRATION"
    assert row.open_option_theta_per_day >= row.underlying.open_call_theta_per_day

    rendered = templates.env.get_template("partials/_underlyings.html").render(
        snapshot=snapshot_with_puts,
        desk_overview=build_desk_overview(snapshot_with_puts),
    )
    ktos_card = rendered.split('id="ktos-workspace"', 1)[1].split("</details>", 1)[0]
    assert "NEAREST 3 BY EXPIRATION" in ktos_card
    assert "1 CALL LINE" in ktos_card
    assert ktos_card.count("underlying-contract-grid") == 1
    assert "contract-call-lane" not in ktos_card
    assert "contract-put-lane" not in ktos_card
    assert 'data-option-side="put"' in ktos_card.split("underlying-priority-options", 1)[1].split(
        "underlying-contract-shelf", 1
    )[0]


def test_name_iv_and_theta_include_open_puts() -> None:
    snapshot = DemoDashboardReader().execute()
    row = next(
        item
        for item in build_desk_overview(snapshot).position_rows
        if item.underlying.symbol == "KTOS"
    )
    put = _put_clock(
        expires_on=date(2026, 8, 21),
        strike=D("60"),
        distance_percent=D("12"),
    )
    heavy = replace(
        row,
        put_clocks=(
            replace(
                put,
                implied_volatility_percent=D("90"),
                contracts=20,
                short_theta_per_day=D("4"),
            ),
        ),
    )

    blind = replace(row, put_clocks=(put,))

    assert row.open_iv_caption == "AVG OPEN IV"
    assert blind.open_iv_caption == "AVG OPEN CALL IV"
    assert heavy.open_iv_caption == "AVG OPEN IV"
    assert heavy.average_open_option_iv_percent != row.average_open_option_iv_percent
    assert heavy.average_open_option_iv_percent > row.average_open_option_iv_percent
    assert heavy.open_option_theta_per_day == row.underlying.open_call_theta_per_day + D("4")


def test_name_open_option_value_now_sums_call_and_put_clocks() -> None:
    snapshot = DemoDashboardReader().execute()
    row = next(
        item
        for item in build_desk_overview(snapshot).position_rows
        if item.underlying.symbol == "KTOS"
    )
    calls = sum((clock.current_option_value for clock in row.underlying.open_call_clocks), D("0"))
    put = _put_clock(
        expires_on=date(2026, 8, 21),
        strike=D("60"),
        distance_percent=D("12"),
    )
    mixed = replace(row, put_clocks=(put,))
    empty = replace(row, put_clocks=(), underlying=replace(row.underlying, open_call_clocks=()))

    assert row.open_option_value_now == calls
    assert mixed.open_option_value_now == calls + put.current_option_value
    assert mixed.open_option_entry_credit == row.open_option_entry_credit + put.entry_credit
    assert empty.open_option_value_now is None
    assert empty.open_option_entry_credit == D("0")

    overflow_puts = (
        put,
        _put_clock(
            expires_on=date(2026, 8, 21),
            strike=D("55"),
            distance_percent=D("19"),
            option_symbol="KTOS  260821P00055000",
        ),
        _put_clock(
            expires_on=date(2026, 9, 18),
            strike=D("50"),
            distance_percent=D("26"),
            option_symbol="KTOS  260918P00050000",
        ),
    )
    crowded = replace(row, put_clocks=overflow_puts)
    assert len(crowded.overflow_options) >= 1
    assert crowded.open_option_value_now == calls + sum(
        (clock.current_option_value for clock in overflow_puts),
        D("0"),
    )

