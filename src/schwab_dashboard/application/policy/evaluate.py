from decimal import Decimal

from schwab_dashboard.application.policy.models import CallPolicy, PolicyFit


def evaluate_policy_fit(
    policy: CallPolicy,
    *,
    strike_buffer_percent: Decimal,
    days_to_expiration: int,
    effective_exit_price: Decimal,
) -> PolicyFit:
    fits_dte = (
        policy.minimum_days_to_expiration <= days_to_expiration <= policy.maximum_days_to_expiration
    )
    fits_buffer = strike_buffer_percent >= policy.minimum_strike_buffer_percent
    exit_fit = (
        effective_exit_price >= policy.acceptable_exit_price
        if policy.acceptable_exit_price is not None
        else None
    )
    checks = (fits_dte, fits_buffer) if exit_fit is None else (fits_dte, fits_buffer, exit_fit)
    passed = sum(checks)
    summary = (
        "Fits declared plan"
        if passed == len(checks)
        else f"{passed}/{len(checks)} declared rules fit"
    )
    return PolicyFit(
        policy_id=policy.policy_id,
        policy_label=policy.label,
        intent_label=policy.intent.label,
        fits_dte=fits_dte,
        fits_strike_buffer=fits_buffer,
        acceptable_exit=exit_fit,
        passed_checks=passed,
        total_checks=len(checks),
        summary=summary,
    )
