from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from schwab_dashboard.application.risk.calculate import calculate_open_risk
from schwab_dashboard.application.risk.models import OpenCallRiskInput
from schwab_dashboard.domain.analytics import DataQuality, ValueStatus
from schwab_dashboard.domain.market import QuoteQuality

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
    assert summary.context.quality is DataQuality.PARTIAL


def test_missing_mark_keeps_obligations_but_marks_result_partial() -> None:
    summary = calculate_open_risk((_call(option_mark=None),))

    assert summary.positions[0].called_away_notional == Decimal("32500")
    assert summary.positions[0].current_liability is None
    assert summary.context.quality is DataQuality.PARTIAL


def test_mixed_quote_timestamps_are_rejected() -> None:
    later = datetime(2026, 8, 9, 20, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="one observed_at"):
        calculate_open_risk((_call(), _call(contract_key="later", observed_at=later)))
