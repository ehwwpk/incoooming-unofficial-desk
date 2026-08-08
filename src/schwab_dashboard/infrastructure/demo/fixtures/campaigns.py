from datetime import date
from decimal import Decimal

from schwab_dashboard.application.dashboard.models import CampaignSummary

D = Decimal


def build_campaigns() -> tuple[CampaignSummary, ...]:
    return (
        CampaignSummary(
            symbol="CVX",
            strategy="Covered calls · 6/7 contracts",
            status="86% covered",
            opened_on=date(2026, 7, 24),
            expires_on=date(2026, 9, 4),
            days_to_expiration=28,
            legs=("-4 Sep 04 $235C", "-2 Sep 18 $225C"),
            net_option_cash=D("2275.00"),
            unrealized_profit_loss=D("360.00"),
            collateral=D("134582.00"),
            return_on_risk_percent=D("1.96"),
            progress_percent=44,
        ),
        CampaignSummary(
            symbol="KTOS",
            strategy="Covered calls · 8/8 contracts",
            status="Fully covered",
            opened_on=date(2026, 7, 31),
            expires_on=date(2026, 9, 18),
            days_to_expiration=42,
            legs=("-5 Sep 18 $75C", "-3 Sep 18 $82.5C"),
            net_option_cash=D("2370.00"),
            unrealized_profit_loss=D("-290.00"),
            collateral=D("52152.00"),
            return_on_risk_percent=D("4.80"),
            progress_percent=29,
        ),
        CampaignSummary(
            symbol="URNM",
            strategy="Covered calls · 4/5 contracts",
            status="80% covered",
            opened_on=date(2026, 8, 7),
            expires_on=date(2026, 9, 18),
            days_to_expiration=42,
            legs=("-4 Sep 18 $67.5C",),
            net_option_cash=D("1695.00"),
            unrealized_profit_loss=D("132.00"),
            collateral=D("27285.00"),
            return_on_risk_percent=D("6.70"),
            progress_percent=7,
        ),
    )
