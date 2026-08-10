from decimal import Decimal

from schwab_dashboard.application.policy.models import (
    CallPolicy,
    RetentionIntent,
    UnderlyingPolicy,
)

D = Decimal


POLICIES = (
    UnderlyingPolicy(
        symbol="CVX",
        label="Staged income and planned trims",
        policies=(
            CallPolicy(
                "cvx-near-trim",
                "Near trim",
                RetentionIntent.TRIM_REDEPLOY,
                200,
                D("0"),
                14,
                24,
                D("195"),
                False,
                True,
                "Shorter calls when premium expands; assignment can release capital.",
            ),
            CallPolicy(
                "cvx-far-income",
                "Far income",
                RetentionIntent.ACCEPTABLE_EXIT,
                400,
                D("8"),
                35,
                60,
                D("215"),
                True,
                True,
                "Longer, higher-strike calls retain more upside while collecting premium.",
            ),
        ),
    ),
    UnderlyingPolicy(
        symbol="KTOS",
        label="Upside preservation",
        policies=(
            CallPolicy(
                "ktos-preserve-near",
                "$75 short cycle",
                RetentionIntent.PRESERVE,
                500,
                D("15"),
                14,
                35,
                D("75"),
                True,
                True,
                "Two-to-five-week calls with a deliberately high strike.",
            ),
            CallPolicy(
                "ktos-preserve-far",
                "$90 long cycle",
                RetentionIntent.PRESERVE,
                300,
                D("30"),
                42,
                60,
                D("90"),
                True,
                True,
                "Six-to-eight-week calls reserve substantially more upside.",
            ),
            CallPolicy(
                "ktos-legacy",
                "Historical fixture",
                RetentionIntent.NEUTRAL,
                0,
                D("0"),
                0,
                90,
                None,
                False,
                False,
                "Historical demo record retained for lifecycle testing.",
            ),
        ),
    ),
    UnderlyingPolicy(
        symbol="URNM",
        label="Higher-strike income",
        policies=(
            CallPolicy(
                "urnm-income",
                "Income ladder",
                RetentionIntent.NEUTRAL,
                400,
                D("15"),
                21,
                56,
                None,
                True,
                True,
                "Current fixture posture until a more specific policy is declared.",
            ),
        ),
    ),
)


def build_policies() -> tuple[UnderlyingPolicy, ...]:
    return POLICIES
