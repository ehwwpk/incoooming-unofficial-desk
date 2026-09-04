from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from schwab_dashboard.application.risk.calculate import calculate_open_risk
from schwab_dashboard.application.risk.models import (
    OpenCallRiskInput,
    UnderlyingEquityRiskInput,
)
from schwab_dashboard.application.risk.projection import build_open_risk_summary
from schwab_dashboard.domain.analytics import DataQuality, ValueStatus
from schwab_dashboard.domain.market import QuoteQuality
from schwab_dashboard.infrastructure.demo.dashboard import DemoDashboardReader

NOW = datetime(2026, 8, 9, 20, 0, tzinfo=UTC)


def _call(**changes: object) -> OpenCallRiskInput:
    values: dict[str, object] = {
        "contract_key": "ktos-call-65",
        "symbol": "KTOS",
        "contracts_short": Decimal("5"),
        "premium_multiplier": Decimal("100"),
        "deliverable_share_quantity": Decimal("100"),
        "strike": Decimal("65"),
        "underlying_price": Decimal("60.77"),
        "observed_at": NOW,
        "quote_quality": QuoteQuality.COMPLETE,
        "entry_credit": Decimal("2.45"),
        "option_mark": Decimal("3.30"),
        "bid": Decimal("3.20"),
        "ask": Decimal("3.40"),
        "delta": Decimal("0.41"),
        "gamma": Decimal("0.022"),
        "theta": Decimal("-0.065"),
        "vega": Decimal("0.104"),
    }
    values.update(changes)
    return OpenCallRiskInput(**values)  # type: ignore[arg-type]


def test_open_risk_keeps_obligation_liability_and_greeks_distinct() -> None:
    summary = calculate_open_risk((_call(),))
    row = summary.positions[0]

    assert row.obligated_shares == Decimal("500")
    assert row.called_away_notional == Decimal("32500")
    assert row.current_liability == Decimal("1650.00")
    assert row.open_mark_profit_loss == Decimal("-425.00")
    assert row.theta_estimate_per_day == Decimal("32.500")
    assert row.delta_share_equivalent == Decimal("-205.00")
    assert row.dollar_delta_for_one_percent_move == Decimal("-124.5785")
    assert summary.context.status is ValueStatus.ESTIMATED
    assert summary.context.quality is DataQuality.COMPLETE


def test_missing_greek_reduces_coverage_instead_of_becoming_zero() -> None:
    summary = calculate_open_risk(
        (
            _call(),
            _call(
                contract_key="ktos-call-75",
                contracts_short=Decimal("3"),
                strike=Decimal("75"),
                delta=None,
                theta=None,
            ),
        )
    )

    assert float(summary.delta_coverage_percent) == pytest.approx(62.5)
    assert float(summary.theta_coverage_percent) == pytest.approx(62.5)
    assert summary.option_delta_share_equivalent is None
    assert summary.theta_estimate_per_day is None
    assert summary.underlyings[0].option_delta_share_equivalent is None
    assert summary.underlyings[0].theta_estimate_per_day is None
    assert summary.context.quality is DataQuality.PARTIAL


def test_missing_mark_keeps_obligations_but_marks_result_partial() -> None:
    summary = calculate_open_risk((_call(option_mark=None),))

    assert summary.positions[0].called_away_notional == Decimal("32500")
    assert summary.positions[0].current_liability is None
    assert summary.current_liability is None
    assert summary.context.quality is DataQuality.PARTIAL


def test_mixed_quote_timestamps_are_preserved_as_a_freshness_range() -> None:
    later = datetime(2026, 8, 9, 20, 1, tzinfo=UTC)
    summary = calculate_open_risk((_call(), _call(contract_key="later", observed_at=later)))

    assert summary.oldest_quote_at == NOW
    assert summary.newest_quote_at == later
    assert summary.context.as_of == NOW


def test_short_put_delta_is_positive_while_vega_stays_negative() -> None:
    summary = calculate_open_risk(
        (
            _call(
                contract_key="ktos-put-55",
                contracts_short=Decimal("2"),
                option_type="PUT",
                strike=Decimal("55"),
                delta=Decimal("-0.30"),
                theta=Decimal("-0.04"),
                vega=Decimal("0.08"),
            ),
        )
    )

    row = summary.positions[0]
    assert row.delta_share_equivalent == Decimal("60.00")
    assert row.theta_estimate_per_day == Decimal("8.00")
    assert row.vega_per_volatility_point == Decimal("-16.00")


def test_book_price_lens_combines_shares_with_known_option_delta() -> None:
    summary = calculate_open_risk(
        (_call(contracts_short=Decimal("1")),),
        equities=(
            UnderlyingEquityRiskInput(
                symbol="KTOS",
                shares=Decimal("500"),
                underlying_price=Decimal("60.77"),
            ),
        ),
    )

    assert summary.net_delta_share_equivalent == Decimal("459.00")
    assert summary.net_share_exposure_percent == Decimal("91.800")
    assert summary.estimated_value_change_for_one_percent_move == Decimal("278.9343")
    assert summary.underlyings[0].net_delta_share_equivalent == Decimal("459.00")
    assert summary.underlyings[0].net_share_exposure_percent == Decimal("91.800")


def test_iv_shock_is_translated_into_current_theta_days() -> None:
    summary = calculate_open_risk(
        (
            _call(
                contracts_short=Decimal("1"),
                theta=Decimal("-0.10"),
                vega=Decimal("0.25"),
            ),
        ),
        equities=(
            UnderlyingEquityRiskInput(
                symbol="KTOS",
                shares=Decimal("100"),
                underlying_price=Decimal("60.77"),
            ),
        ),
    )

    assert summary.theta_estimate_per_day == Decimal("10.00")
    assert summary.vega_per_volatility_point == Decimal("-25.00")
    assert summary.iv_point_in_theta_days == Decimal("2.5")
    assert summary.underlyings[0].iv_point_in_theta_days == Decimal("2.5")
    assert summary.largest_absolute_vega_symbol == "KTOS"


def test_missing_delta_does_not_publish_a_false_shares_only_price_estimate() -> None:
    summary = calculate_open_risk(
        (_call(delta=None),),
        equities=(
            UnderlyingEquityRiskInput(
                symbol="KTOS",
                shares=Decimal("500"),
                underlying_price=Decimal("60.77"),
            ),
        ),
    )

    assert summary.estimated_value_change_for_one_percent_move is None
    assert summary.net_delta_share_equivalent is None
    assert summary.underlyings[0].estimated_value_change_for_one_percent_move is None
    assert summary.underlyings[0].net_delta_share_equivalent is None


def test_risk_projection_keeps_premium_scale_separate_from_share_delivery() -> None:
    snapshot = DemoDashboardReader().execute()
    underlying = snapshot.underlyings[0]
    clock = replace(underlying.open_call_clocks[0], contracts=2, contract_multiplier=Decimal("150"))
    adjusted = replace(
        snapshot,
        underlyings=(replace(underlying, open_call_clocks=(clock,)),),
    )

    summary = build_open_risk_summary(adjusted)

    assert summary is not None
    assert summary.positions[0].obligated_shares == Decimal("200")
    assert summary.positions[0].delta_share_equivalent == -clock.delta * Decimal("300")


def test_unknown_adjusted_delivery_withholds_share_obligation_but_keeps_option_risk() -> None:
    item = replace(
        _call(),
        premium_multiplier=Decimal("150"),
        deliverable_share_quantity=None,
    )

    summary = calculate_open_risk((item,))

    assert summary.positions[0].obligated_shares is None
    assert summary.positions[0].called_away_notional is None
    assert summary.obligated_shares is None
    assert summary.called_away_notional is None
    assert summary.positions[0].current_liability == Decimal("2475.00")
    assert summary.positions[0].delta_share_equivalent == Decimal("-307.50")
    assert summary.context.quality is DataQuality.PARTIAL
