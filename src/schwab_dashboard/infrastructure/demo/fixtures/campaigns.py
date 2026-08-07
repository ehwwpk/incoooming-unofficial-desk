from datetime import date
from decimal import Decimal

from schwab_dashboard.application.dashboard.models import CampaignSummary

D = Decimal


def build_campaigns() -> tuple[CampaignSummary, ...]:
    return (
        CampaignSummary(
            symbol="NVDA",
            strategy="Covered call",
            status="Managing",
            opened_on=date(2026, 7, 24),
            expires_on=date(2026, 8, 14),
            days_to_expiration=7,
            legs=("+300 shares", "-3 Aug 14 180C"),
            realized_income=D("876.00"),
            unrealized_profit_loss=D("444.00"),
            collateral=D("50475.00"),
            return_on_risk_percent=D("2.62"),
            progress_percent=68,
        ),
        CampaignSummary(
            symbol="AMZN",
            strategy="Cash-secured put",
            status="On track",
            opened_on=date(2026, 7, 31),
            expires_on=date(2026, 8, 21),
            days_to_expiration=14,
            legs=("-2 Aug 21 200P",),
            realized_income=D("690.00"),
            unrealized_profit_loss=D("260.00"),
            collateral=D("40000.00"),
            return_on_risk_percent=D("2.38"),
            progress_percent=61,
        ),
        CampaignSummary(
            symbol="SPY",
            strategy="Iron condor",
            status="Watch",
            opened_on=date(2026, 8, 3),
            expires_on=date(2026, 9, 18),
            days_to_expiration=42,
            legs=("+2 590P / -2 595P", "-2 650C / +2 655C"),
            realized_income=D("420.00"),
            unrealized_profit_loss=D("210.00"),
            collateral=D("1600.00"),
            return_on_risk_percent=D("26.25"),
            progress_percent=50,
        ),
    )
