from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from schwab_dashboard.application.volatility.calculate import analyze_volatility_history
from schwab_dashboard.application.volatility.models import DailyVolatilityObservation
from schwab_dashboard.domain.analytics import DataQuality


def _observation(day: int, close: str, iv: str | None) -> DailyVolatilityObservation:
    return DailyVolatilityObservation(
        source_id=f"snapshot-{day}",
        session_date=date(2026, 8, day),
        observed_at=datetime(2026, 8, day, 20, 0, tzinfo=UTC),
        close=Decimal(close),
        normalized_implied_volatility=Decimal(iv) if iv is not None else None,
    )


def test_volatility_summary_uses_log_returns_and_explicit_midrank_percentile() -> None:
    result = analyze_volatility_history(
        (
            _observation(3, "100", "0.40"),
            _observation(4, "102", "0.50"),
            _observation(5, "101", "0.50"),
            _observation(6, "104", "0.60"),
        )
    )

    assert result.return_count == 3
    assert result.annualized_realized_volatility is not None
    assert float(result.annualized_realized_volatility) == pytest.approx(0.3240135, rel=1e-6)
    assert result.implied_volatility_rank_percent == Decimal("100")
    assert result.implied_volatility_percentile == Decimal("100")
    assert result.implied_minus_realized is not None
    assert result.context.method_version == "1.0.0"
    assert result.context.source_ids[-1] == "snapshot-6"


def test_flat_iv_range_is_unavailable_instead_of_dividing_by_zero() -> None:
    result = analyze_volatility_history(
        (
            _observation(3, "100", "0.50"),
            _observation(4, "101", "0.50"),
            _observation(5, "102", "0.50"),
        )
    )

    assert result.implied_volatility_rank_percent is None
    assert result.implied_volatility_percentile == Decimal("50.0")


def test_duplicate_market_sessions_are_rejected() -> None:
    with pytest.raises(ValueError, match="unique session dates"):
        analyze_volatility_history(
            (
                _observation(3, "100", "0.40"),
                _observation(3, "101", "0.50"),
            )
        )


def test_empty_history_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one"):
        analyze_volatility_history(())


def test_short_history_is_explicitly_partial() -> None:
    result = analyze_volatility_history((_observation(3, "100", "0.50"),))

    assert result.annualized_realized_volatility is None
    assert result.context.quality is DataQuality.PARTIAL
