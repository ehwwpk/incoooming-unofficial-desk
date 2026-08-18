from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal

from schwab_dashboard.application.alerts import build_desk_alerts
from schwab_dashboard.application.alerts.rules import (
    evaluate_call_expiration_pressure,
    evaluate_call_expiration_pressures,
    evaluate_fast_move,
    evaluate_short_put_pressure,
)
from schwab_dashboard.application.dashboard.models import LiveOpenOptionPosition
from schwab_dashboard.application.market_time import OptionSessionState
from schwab_dashboard.infrastructure.demo.dashboard import DemoDashboardReader

D = Decimal


def _short_put(*, dte: int = 6, spot: str = "48", strike: str = "50") -> LiveOpenOptionPosition:
    as_of = date(2026, 8, 11)
    spot_value = D(spot)
    strike_value = D(strike)
    distance = spot_value - strike_value
    return LiveOpenOptionPosition(
        account_mask="...1234",
        option_symbol="XYZ   260817P00050000",
        underlying_symbol="XYZ",
        contracts=2,
        expires_on=as_of + timedelta(days=dte),
        days_to_expiration=dte,
        strike=strike_value,
        entry_credit_per_share=D("1.25"),
        estimated_mark_per_share=D("2.10"),
        market_value=D("-420"),
        open_profit_loss=D("-170"),
        day_profit_loss=D("-40"),
        underlying_price=spot_value,
        strike_distance_per_share=distance,
        strike_distance_percent=distance / spot_value * D("100"),
        option_type="PUT",
    )


def test_short_put_alert_reports_time_distance_and_assignment_notional() -> None:
    alert = evaluate_short_put_pressure(_short_put())

    assert alert is not None
    assert alert.reason_code == "short_put_expiration_proximity"
    assert alert.level == "attention"
    assert alert.headline == "XYZ is through your $50 put"
    assert "$10,000" in alert.message
    assert "before premium" not in alert.message
    assert alert.message.endswith("Keep your paws hot.")
    assert [(fact.label, fact.value) for fact in alert.facts] == [
        ("STOCK / STRIKE", "$48.00 / $50"),
        ("STRIKE DISTANCE", "$2.00 / 4.2%"),
        ("TIME LEFT", "6 DTE"),
        ("MARK / CREDIT", "$2.10 / $1.25"),
    ]
    assert "not a claim about cash" in alert.method_note.lower()


def test_fast_move_alert_names_the_sale_and_keeps_the_personality_brief() -> None:
    snapshot = DemoDashboardReader().execute()
    ktos = next(item for item in snapshot.underlyings if item.symbol == "KTOS")
    call = replace(
        ktos.open_call_clocks[0],
        strike=D("68"),
        underlying_at_sale=ktos.current_price / D("1.1"),
        strike_distance_per_share=D("4.32"),
        strike_distance_percent=D("6.78"),
    )
    prices = list(ktos.price_points)
    prices[-6] = replace(prices[-6], price=ktos.current_price / D("1.2"))
    underlying = replace(
        ktos,
        open_call_clocks=(call,),
        price_points=tuple(prices),
    )

    alert = evaluate_fast_move(underlying)

    assert alert is not None
    assert alert.headline == "KTOS is running at your $68 call"
    assert "since you sold the $68 call" in alert.message
    assert "Rude timing." in alert.message
    assert "put back on the desk" in alert.message
    assert "moved fast after the sale" not in alert.message
    assert alert.roll_source_option_symbol == call.record_id
    assert alert.roll_option_side is not None
    assert alert.roll_option_side.value == "call"
    pressure = next(fact.value for fact in alert.facts if fact.label == "REVIEW PRESSURE")
    assert pressure.split(" · ", 1)[0] in {"LOW", "MODERATE", "ELEVATED", "HIGH"}


def test_short_put_rule_stays_quiet_when_strike_has_room_or_time() -> None:
    assert evaluate_short_put_pressure(_short_put(dte=30, spot="55")) is None
    assert evaluate_short_put_pressure(_short_put(dte=10, spot="55")) is None


def test_nibwick_stops_offering_expired_friday_trading_actions() -> None:
    snapshot = DemoDashboardReader().execute()
    ktos = next(item for item in snapshot.underlyings if item.symbol == "KTOS")
    closed_call = replace(
        ktos.open_call_clocks[0],
        days_to_expiration=0,
        strike_distance_per_share=D("0.50"),
        strike_distance_percent=D("0.8"),
        session_state=OptionSessionState.CLOSED_PENDING_SETTLEMENT,
    )
    closed_underlying = replace(ktos, open_call_clocks=(closed_call,))
    closed_put = replace(
        _short_put(dte=0, spot="49.75"),
        session_state=OptionSessionState.CLOSED_PENDING_SETTLEMENT,
    )

    assert evaluate_call_expiration_pressure(closed_underlying) is None
    assert evaluate_fast_move(closed_underlying) is None
    assert evaluate_short_put_pressure(closed_put) is None
    assert (
        build_desk_alerts(
            (closed_underlying,),
            as_of=snapshot.as_of.date(),
            put_positions=(closed_put,),
        )
        == ()
    )


def test_alert_identity_changes_only_across_material_state_bands() -> None:
    base = _short_put(dte=6, spot="48")
    same_band = replace(
        base,
        underlying_price=D("48.25"),
        strike_distance_per_share=D("-1.75"),
        strike_distance_percent=D("-3.63"),
    )
    later_band = replace(base, days_to_expiration=8, expires_on=date(2026, 8, 19))

    first = evaluate_short_put_pressure(base)
    second = evaluate_short_put_pressure(same_band)
    changed = evaluate_short_put_pressure(later_band)

    assert first is not None and second is not None and changed is not None
    assert first.alert_id == second.alert_id
    assert first.alert_id != changed.alert_id


def test_call_expiration_rule_fills_the_slow_move_gap_without_duplicate_notes() -> None:
    snapshot = DemoDashboardReader().execute()
    ktos = next(item for item in snapshot.underlyings if item.symbol == "KTOS")
    call = replace(
        ktos.open_call_clocks[0],
        strike=D("65"),
        strike_distance_per_share=D("1.27"),
        strike_distance_percent=D("2.09"),
        days_to_expiration=6,
    )
    near = replace(ktos, open_call_clocks=(call,))

    alert = evaluate_call_expiration_pressure(near)
    combined = build_desk_alerts((near,), as_of=snapshot.as_of.date())

    assert alert is not None
    assert alert.reason_code == "call_expiration_proximity"
    assert "6 days left" in alert.message
    assert "air" not in alert.headline.lower()
    assert "air" not in alert.message.lower()
    assert "2.1% below your $65 call" in alert.headline
    assert "$1.27/share below your $65 call" in alert.message
    assert alert.message.endswith("Keep an eye on it.")
    assert len(combined) == 1


def test_call_expiration_rule_checks_every_contract_before_ranking() -> None:
    snapshot = DemoDashboardReader().execute()
    ktos = next(item for item in snapshot.underlyings if item.symbol == "KTOS")
    closest_but_too_early = replace(
        ktos.open_call_clocks[0],
        record_id="closest-too-early",
        days_to_expiration=30,
        strike_distance_per_share=D("0.64"),
        strike_distance_percent=D("1"),
    )
    farther_but_expiring = replace(
        ktos.open_call_clocks[1],
        record_id="farther-expiring",
        days_to_expiration=5,
        strike_distance_per_share=D("3.18"),
        strike_distance_percent=D("5"),
    )
    underlying = replace(
        ktos,
        open_call_clocks=(closest_but_too_early, farther_but_expiring),
    )

    alert = evaluate_call_expiration_pressure(underlying)

    assert alert is not None
    assert alert.level == "watch"
    assert "5 days left" in alert.message
    assert next(fact.value for fact in alert.facts if fact.label == "TIME LEFT") == "5 DTE"


def test_call_expiration_rule_keeps_each_qualifying_contract_visible() -> None:
    snapshot = DemoDashboardReader().execute()
    cvx = next(item for item in snapshot.underlyings if item.symbol == "CVX")
    first = replace(
        cvx.open_call_clocks[0],
        record_id="CVX-205-CALL",
        strike=D("205"),
        strike_distance_per_share=D("6.70"),
        strike_distance_percent=D("3.38"),
        days_to_expiration=14,
    )
    second = replace(
        cvx.open_call_clocks[1],
        record_id="CVX-2075-CALL",
        strike=D("207.5"),
        strike_distance_per_share=D("9.20"),
        strike_distance_percent=D("4.64"),
        days_to_expiration=0,
    )
    underlying = replace(cvx, open_call_clocks=(first, second))

    contract_alerts = evaluate_call_expiration_pressures(underlying)
    combined = build_desk_alerts((underlying,), as_of=snapshot.as_of.date())

    assert {alert.roll_source_option_symbol for alert in contract_alerts} == {
        "CVX-205-CALL",
        "CVX-2075-CALL",
    }
    assert {alert.roll_source_option_symbol for alert in combined} == {
        "CVX-205-CALL",
        "CVX-2075-CALL",
    }


def test_build_alerts_limits_short_put_notes_to_one_per_symbol() -> None:
    farther = replace(
        _short_put(dte=12, spot="49"),
        option_symbol="XYZ   260823P00050000",
        expires_on=date(2026, 8, 23),
    )
    alerts = build_desk_alerts((), as_of=date(2026, 8, 11), put_positions=(_short_put(), farther))

    assert len(alerts) == 1
    assert alerts[0].symbol == "XYZ"


def test_build_alerts_keeps_a_directional_note_for_every_qualifying_symbol() -> None:
    snapshot = DemoDashboardReader().execute()
    as_of = snapshot.as_of.date()
    qualifying = []
    for underlying in snapshot.underlyings:
        call = replace(
            underlying.open_call_clocks[0],
            expires_on=as_of + timedelta(days=6),
            days_to_expiration=6,
            strike=underlying.current_price * D("1.02"),
            strike_distance_per_share=underlying.current_price * D("0.02"),
            strike_distance_percent=D("2"),
        )
        qualifying.append(replace(underlying, open_call_clocks=(call,)))

    alerts = build_desk_alerts(tuple(qualifying), as_of=as_of)

    assert {alert.symbol for alert in alerts} == {"CVX", "KTOS", "URNM"}
    assert len(alerts) == 3
