from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

ZERO = Decimal("0")
HALF = Decimal("0.5")
HUNDRED = Decimal("100")


@dataclass(frozen=True, slots=True)
class PriceTimeRead:
    """One short option's modeled stock-move effect beside one day of theta.

    ``price_effect`` is a signed position-value estimate for the latest
    underlying session move. ``theta_per_day`` is the current one-day theta
    estimate. ``up_one_dollar_effect`` and ``down_one_dollar_effect`` show the
    local, gamma-adjusted position-value effect of the next one-dollar move in
    the underlying. None of these values is cash received or a forecast.
    """

    price_effect: Decimal | None
    up_one_dollar_effect: Decimal | None
    down_one_dollar_effect: Decimal | None
    theta_per_day: Decimal | None
    price_plus_one_day: Decimal | None
    price_effect_in_theta_days: Decimal | None
    delta_pressure_change: Decimal | None
    delta_pressure_label: str | None
    five_session_move_percent: Decimal | None
    adverse_move_direction: str | None
    model_coverage_percent: Decimal
    gamma_adjusted: bool

    @property
    def consequence(self) -> str:
        if self.price_effect is None:
            return "Price effect needs a current underlying move."
        if self.theta_per_day is None or self.theta_per_day <= ZERO:
            return "Price effect only; theta is unavailable."
        if abs(self.price_effect) <= max(Decimal("1"), self.theta_per_day / Decimal("10")):
            return "Price stayed quiet; time did most of the work."
        if self.price_effect > ZERO:
            return "Price and time both helped the short option."
        assert self.price_effect_in_theta_days is not None
        return f"Price move cost about {_compact(self.price_effect_in_theta_days)} days of theta."

    @property
    def compact_consequence(self) -> str:
        """A terminal-sized read that preserves the decision consequence."""

        if self.price_effect is None:
            return "PRICE MOVE UNAVAILABLE"
        if self.theta_per_day is None or self.theta_per_day <= ZERO:
            return "PRICE EFFECT ONLY"
        if abs(self.price_effect) <= max(Decimal("1"), self.theta_per_day / Decimal("10")):
            return "TIME DID THE WORK"
        if self.price_effect > ZERO:
            return "PRICE + TIME HELPED"
        assert self.price_effect_in_theta_days is not None
        return f"PRICE COST {_compact(self.price_effect_in_theta_days)} THETA-DAYS"

    @property
    def pressure_summary(self) -> str:
        if self.delta_pressure_label is None or self.delta_pressure_change is None:
            return "Five-session price pressure needs complete delta, gamma, and price inputs."
        amount = abs(self.delta_pressure_change)
        if self.delta_pressure_label == "STEADY":
            return (
                "The five-session stock move was roughly flat versus this position's adverse "
                "direction."
            )
        if self.adverse_move_direction is None:
            book_direction = "toward" if self.delta_pressure_label == "RISING" else "away from"
            return (
                f"Across the open book, more five-session stock pressure moved {book_direction} "
                "the positions' risky sides. Open a name for contract-level context."
            )
        move_direction = (
            self.adverse_move_direction.lower()
        )
        weekly_path = "that way" if self.delta_pressure_label == "RISING" else "away from it"
        return (
            f"For this position, {move_direction} is the risky direction. The stock moved "
            f"{weekly_path} over five sessions. At today's gamma, another $1 {move_direction} "
            f"would add about ${_compact(amount)} to the loss effect of the following $1 move."
        )

    @property
    def compact_pressure(self) -> str:
        if self.delta_pressure_label is None:
            return "5D PRICE PRESSURE PARTIAL"
        trend = self.pressure_trend_plain or "PARTIAL"
        if self.adverse_move_direction:
            return f"5D {self.adverse_move_direction}-MOVE RISK {trend}"
        return f"5D PRICE RISK {trend}"

    @property
    def pressure_trend_plain(self) -> str | None:
        if self.delta_pressure_label == "RISING":
            return "HEATING"
        if self.delta_pressure_label == "EASING":
            return "COOLING"
        if self.delta_pressure_label == "STEADY":
            return "QUIET"
        return None

    @property
    def pressure_trend_label(self) -> str:
        return self.pressure_trend_plain or "PARTIAL"

    @property
    def pressure_face_line(self) -> str | None:
        if self.five_session_move_percent is None:
            return None
        if self.delta_pressure_label is None or self.absolute_pressure_change is None:
            return "5D PRICE PRESSURE PARTIAL"
        trend = self.pressure_trend_plain or "PARTIAL"
        parts = [f"5D STOCK {_signed_percent(self.five_session_move_percent)}"]
        if trend == "HEATING":
            parts.append(f"+${_compact(self.absolute_pressure_change)}/NEXT $1")
        elif trend == "COOLING":
            parts.append(f"${_compact(self.absolute_pressure_change)}/NEXT $1 EASED")
        return " · ".join(parts)

    @property
    def pressure_plain_line(self) -> str | None:
        if self.delta_pressure_label is None:
            return (
                "Weekly price-pressure read is partial; missing model inputs stay blank."
            )
        if self.five_session_move_percent is None:
            return None
        move_direction = (
            self.adverse_move_direction.lower()
            if self.adverse_move_direction
            else "price"
        )
        if self.delta_pressure_label == "STEADY":
            return (
                f"The five-session stock move was roughly flat versus this position's "
                f"{move_direction}-move side."
            )
        if self.adverse_move_direction is None:
            book_direction = "toward" if self.delta_pressure_label == "RISING" else "away from"
            return (
                f"Across the open book, more five-session stock pressure moved {book_direction} "
                "the positions' risky sides. Open a name for contract-level context."
            )
        weekly_path = "that way" if self.delta_pressure_label == "RISING" else "away from it"
        if self.delta_pressure_label == "RISING":
            assert self.absolute_pressure_change is not None
            return (
                f"Stock moved {weekly_path} over five sessions. "
                f"{self.adverse_move_direction}-move pressure is heating; another $1 "
                f"{move_direction} adds about ${_compact(self.absolute_pressure_change)} "
                "to the hurt."
            )
        assert self.delta_pressure_label == "EASING"
        return (
            f"Stock moved {weekly_path} over five sessions. "
            f"{self.adverse_move_direction}-move pressure is cooling."
        )

    @property
    def session_face_line(self) -> str:
        return self.consequence

    @property
    def absolute_pressure_change(self) -> Decimal | None:
        return abs(self.delta_pressure_change) if self.delta_pressure_change is not None else None

    @property
    def gamma_note(self) -> str:
        if self.delta_pressure_label == "RISING":
            return "The stock moved toward the risky side; current gamma can steepen the next move."
        if self.delta_pressure_label == "EASING":
            return "The stock moved away from the risky side; current price pressure has eased."
        if self.delta_pressure_label == "STEADY":
            return "The five-session stock move was roughly flat versus the risky side."
        return "A weekly gamma direction needs a price reference and complete Greeks."

    @property
    def book_read(self) -> str:
        """A concise book-level interpretation for the Risk Lens.

        The aggregate read deliberately avoids pretending a mixed call-and-put
        book has one universal risky direction. Contract-level direction stays
        with each position; this sentence only describes the balance of recent
        pressure across the open book.
        """

        if self.delta_pressure_label == "RISING":
            return (
                "More contracts moved the wrong way this week. Current gamma makes the next "
                "adverse $1 matter more; the rows below show where."
            )
        if self.delta_pressure_label == "EASING":
            return (
                "More contracts gained breathing room this week. Price pressure eased; the "
                "rows below show what still needs watching."
            )
        if self.delta_pressure_label == "STEADY":
            return (
                "The book mostly held its ground this week. Time decay did more of the work; "
                "the rows below show where risk still sits."
            )
        return (
            "The weekly pressure read is partial. The rows below keep missing model inputs "
            "blank instead of filling the gaps with guesses."
        )


def build_price_time_read(
    *,
    position_delta: Decimal | None,
    position_gamma: Decimal | None,
    theta_per_day: Decimal | None,
    current_underlying_price: Decimal | None,
    previous_close: Decimal | None,
    weekly_reference_price: Decimal | None,
) -> PriceTimeRead:
    """Build a signed, position-scaled price-versus-time explanation.

    The latest-session price estimate integrates back from current delta. When
    gamma is available, a second-order term avoids pretending delta stayed
    constant over the whole move. The weekly cue estimates how much absolute
    delta pressure changed as the underlying moved from its five-session
    reference. The weekly cue deliberately uses the direction of the observed
    stock move rather than extrapolating today's gamma backward through five
    sessions. Current gamma is only a local sensitivity and cannot reconstruct
    historical delta. The cue is context, not a probability or timing signal.
    """

    up_one_dollar_effect: Decimal | None = None
    down_one_dollar_effect: Decimal | None = None
    if position_delta is not None:
        up_one_dollar_effect = position_delta
        down_one_dollar_effect = -position_delta
        if position_gamma is not None:
            gamma_half = HALF * position_gamma
            up_one_dollar_effect += gamma_half
            down_one_dollar_effect += gamma_half

    price_effect: Decimal | None = None
    gamma_adjusted = False
    if (
        position_delta is not None
        and current_underlying_price is not None
        and previous_close is not None
        and previous_close > ZERO
    ):
        session_move = current_underlying_price - previous_close
        price_effect = position_delta * session_move
        if position_gamma is not None:
            price_effect -= HALF * position_gamma * session_move * session_move
            gamma_adjusted = True

    one_day = theta_per_day if theta_per_day is not None and theta_per_day >= ZERO else None
    combined = price_effect + one_day if price_effect is not None and one_day is not None else None
    theta_days = (
        abs(price_effect) / one_day
        if price_effect is not None and one_day is not None and one_day > ZERO
        else None
    )

    adverse_move_direction: str | None = None
    if up_one_dollar_effect is not None and down_one_dollar_effect is not None:
        if up_one_dollar_effect < down_one_dollar_effect:
            adverse_move_direction = "UP"
        elif down_one_dollar_effect < up_one_dollar_effect:
            adverse_move_direction = "DOWN"

    pressure_change: Decimal | None = None
    pressure_label: str | None = None
    five_session_move_percent: Decimal | None = None
    if (
        position_gamma is not None
        and adverse_move_direction is not None
        and current_underlying_price is not None
        and weekly_reference_price is not None
        and weekly_reference_price > ZERO
    ):
        weekly_move = current_underlying_price - weekly_reference_price
        five_session_move_percent = weekly_move / weekly_reference_price * HUNDRED
        adverse_move_percent = (
            five_session_move_percent
            if adverse_move_direction == "UP"
            else -five_session_move_percent
        )
        pressure_label = (
            "RISING"
            if adverse_move_percent > Decimal("0.25")
            else "EASING"
            if adverse_move_percent < Decimal("-0.25")
            else "STEADY"
        )
        local_acceleration = abs(position_gamma)
        pressure_change = (
            local_acceleration
            if pressure_label == "RISING"
            else -local_acceleration
            if pressure_label == "EASING"
            else ZERO
        )

    covered = sum(
        value is not None
        for value in (
            price_effect,
            one_day,
            pressure_change,
        )
    )
    return PriceTimeRead(
        price_effect=price_effect,
        up_one_dollar_effect=up_one_dollar_effect,
        down_one_dollar_effect=down_one_dollar_effect,
        theta_per_day=one_day,
        price_plus_one_day=combined,
        price_effect_in_theta_days=theta_days,
        delta_pressure_change=pressure_change,
        delta_pressure_label=pressure_label,
        five_session_move_percent=five_session_move_percent,
        adverse_move_direction=adverse_move_direction,
        model_coverage_percent=Decimal(covered) / Decimal("3") * HUNDRED,
        gamma_adjusted=gamma_adjusted,
    )


def aggregate_price_time_reads(reads: tuple[PriceTimeRead, ...]) -> PriceTimeRead | None:
    if not reads:
        return None

    price_values = tuple(row.price_effect for row in reads if row.price_effect is not None)
    up_move_values = tuple(
        row.up_one_dollar_effect for row in reads if row.up_one_dollar_effect is not None
    )
    down_move_values = tuple(
        row.down_one_dollar_effect for row in reads if row.down_one_dollar_effect is not None
    )
    theta_values = tuple(row.theta_per_day for row in reads if row.theta_per_day is not None)
    pressure_values = tuple(
        row.delta_pressure_change for row in reads if row.delta_pressure_change is not None
    )
    five_session_moves = {
        row.five_session_move_percent
        for row in reads
        if row.five_session_move_percent is not None
    }
    adverse_directions = {
        row.adverse_move_direction for row in reads if row.adverse_move_direction is not None
    }
    price = sum(price_values, ZERO) if price_values else None
    up_move = sum(up_move_values, ZERO) if up_move_values else None
    down_move = sum(down_move_values, ZERO) if down_move_values else None
    theta = sum(theta_values, ZERO) if theta_values else None
    pressure = sum(pressure_values, ZERO) if pressure_values else None
    combined = price + theta if price is not None and theta is not None else None
    theta_days = (
        abs(price) / theta if price is not None and theta is not None and theta > ZERO else None
    )
    if pressure is None:
        pressure_label = None
    else:
        threshold = max(
            Decimal("1"), sum((abs(value) for value in pressure_values), ZERO) * Decimal("0.05")
        )
        pressure_label = (
            "RISING" if pressure > threshold else "EASING" if pressure < -threshold else "STEADY"
        )
    complete_parts = len(price_values) + len(theta_values) + len(pressure_values)
    total_parts = len(reads) * 3
    return PriceTimeRead(
        price_effect=price,
        up_one_dollar_effect=up_move,
        down_one_dollar_effect=down_move,
        theta_per_day=theta,
        price_plus_one_day=combined,
        price_effect_in_theta_days=theta_days,
        delta_pressure_change=pressure,
        delta_pressure_label=pressure_label,
        five_session_move_percent=(
            next(iter(five_session_moves)) if len(five_session_moves) == 1 else None
        ),
        adverse_move_direction=(
            next(iter(adverse_directions)) if len(adverse_directions) == 1 else None
        ),
        model_coverage_percent=(
            Decimal(complete_parts) / Decimal(total_parts) * HUNDRED if total_parts else ZERO
        ),
        gamma_adjusted=any(row.gamma_adjusted for row in reads),
    )


def _compact(value: Decimal) -> str:
    rendered = f"{value.quantize(Decimal('0.1')):f}"
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _signed_percent(value: Decimal) -> str:
    rendered = _compact(value)
    prefix = "+" if value > ZERO else ""
    return f"{prefix}{rendered}%"
