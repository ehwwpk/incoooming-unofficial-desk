from __future__ import annotations

import re
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parents[2] / "src" / "schwab_dashboard" / "web" / "static"

ART_ONLY_STYLESHEETS = {"nibwick-promenade.css", "sources-art.css"}
ART_ONLY_SELECTORS = {".nibwick-obstacle", ".nibwick pre", ".nibwick-tick"}
MIN_FUNCTIONAL_PX = 7.0

FONT_SIZE_PATTERN = re.compile(
    r"(?:font-size\s*:\s*|font\s*:[^;{}]*?\s)"
    r"(?P<size>\d*\.?\d+)(?P<unit>px|rem)"
)


def _to_pixels(size: str, unit: str) -> float:
    value = float(size)
    return value * 16 if unit == "rem" else value


def _contrast_ratio(foreground: str, background: str) -> float:
    def luminance(hex_color: str) -> float:
        channels = [int(hex_color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [
            channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
            for channel in channels
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    lighter, darker = sorted((luminance(foreground), luminance(background)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def test_functional_css_text_never_falls_below_seven_pixels() -> None:
    violations: list[str] = []
    for stylesheet in STATIC_DIR.glob("*.css"):
        if stylesheet.name in ART_ONLY_STYLESHEETS:
            continue
        for line_number, line in enumerate(
            stylesheet.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if any(selector in line for selector in ART_ONLY_SELECTORS):
                continue
            for match in FONT_SIZE_PATTERN.finditer(line):
                pixels = _to_pixels(match["size"], match["unit"])
                if pixels < MIN_FUNCTIONAL_PX:
                    violations.append(
                        f"{stylesheet.name}:{line_number} resolves to {pixels:.2f}px: "
                        f"{line.strip()}"
                    )

    assert not violations, "\n".join(violations)


def test_typography_tokens_keep_dense_ui_readable() -> None:
    base_css = (STATIC_DIR / "base.css").read_text(encoding="utf-8")
    expected = {
        "--type-micro": ".4375rem",
        "--type-control": ".5rem",
        "--type-meta": ".5625rem",
        "--type-copy-sm": ".625rem",
        "--type-body": ".6875rem",
    }
    for token, value in expected.items():
        assert f"{token}: {value};" in base_css


def test_tertiary_text_meets_small_text_contrast_on_core_surfaces() -> None:
    foreground = "#898c94"
    for background in ("#090a0b", "#0d0f11", "#111317"):
        assert _contrast_ratio(foreground, background) >= 4.5


def _rule_block(stylesheet: str, opener: str) -> str:
    start = stylesheet.index(opener)
    return stylesheet[start : stylesheet.index("}", start)]


def test_name_analytics_gives_leftover_width_to_the_delta_cell() -> None:
    css = (STATIC_DIR / "performance.css").read_text(encoding="utf-8")
    rule = _rule_block(css, ".name-analytics {")
    compact = _rule_block(css, ".name-analytics > div {")
    delta = _rule_block(css, ".name-analytics .name-price-time {")
    pair = _rule_block(css, ".name-analytics .price-time-pair {")

    assert "display: flex" in rule
    assert "flex-wrap: nowrap" in rule
    assert "repeat(7," not in rule
    assert "flex: 0 0 auto" in compact
    assert "padding: 8px 14px 9px" in compact
    assert "flex: 1 1 0%" in delta
    assert "flex-wrap: nowrap" in delta
    assert "justify-content: flex-start" in delta
    assert "padding-inline: 16px" in delta
    assert "min-width: 0" in delta
    assert "nowrap" in pair

    facts = _rule_block(css, ".name-analytics > div:not(.name-price-time) {")
    read = _rule_block(css, ".name-analytics .name-price-time .name-price-time-read {")
    clerk = _rule_block(
        css,
        ".name-analytics .name-price-time .name-price-time-read .price-pressure-line,",
    )
    assert "padding-inline: 16px" in facts
    assert "flex: 1 1 0%" in read
    assert "min-width: 0" in read
    assert "var(--type-copy-sm)" in clerk
    assert "white-space: normal" in clerk
    assert "var(--type-micro)" not in clerk


def test_wave_one_fact_strips_do_not_fake_cell_height() -> None:
    recipes = (
        ("performance.css", ".name-analytics > div {"),
        ("performance.css", ".period-primary > div {"),
        ("open-book.css", ".option-fact-strip > div {"),
        ("desk-overview.css", ".live-position-facts > div, .live-call-row > div {"),
        ("results-cash.css", ".performance-compare-tape > div {"),
    )
    for filename, opener in recipes:
        stylesheet = (STATIC_DIR / filename).read_text(encoding="utf-8")
        rule = _rule_block(stylesheet, opener)
        assert "min-height" not in rule, f"{filename} still pins {opener}"


def test_wave_two_desk_pulse_rows_share_column_grid_and_tight_stacking() -> None:
    desk_css = (STATIC_DIR / "desk-overview.css").read_text(encoding="utf-8")
    observed_rule = _rule_block(desk_css, ".income-observed-bar {")
    assert "repeat(4," in observed_rule, "observed bar should share the 4-column pulse grid"
    pulse_cells = _rule_block(desk_css, ".pulse-income-grid > div,")
    assert "margin-top: auto" not in pulse_cells, (
        "pulse cells should stack tightly, not pin captions"
    )
    assert "align-content: center" in pulse_cells, (
        "pulse cells should vertically center their stack"
    )
    position_cells = _rule_block(desk_css, ".position-book > summary > div {")
    assert "margin-top: auto" not in position_cells, "name row cells should stack tightly"


def test_wave_two_desk_pulse_values_use_body_tokens_not_clamps() -> None:
    desk_css = (STATIC_DIR / "desk-overview.css").read_text(encoding="utf-8")
    value_rule = _rule_block(desk_css, ".pulse-income-grid strong,")
    assert "clamp(" not in value_rule, "pulse income still scales values with clamp()"
    assert "var(--type-body)" in value_rule, "pulse income values should use --type-body"


def test_roll_board_uses_type_tokens_instead_of_raw_sizes() -> None:
    stylesheet = (STATIC_DIR / "open-book.css").read_text(encoding="utf-8")
    roll_board = stylesheet[stylesheet.index(".roll-board-register") :]
    assert "font: 720 11px" not in roll_board
    assert "font: 620 9px" not in roll_board
    assert "font: 750 9px" not in roll_board
    assert "font: 700 12px" not in roll_board
    assert "font: 9px" not in roll_board
    assert ".45rem var(--sans)" not in roll_board
    assert "var(--type-micro)" in roll_board
    assert "var(--type-body)" in roll_board
    assert "var(--type-control)" in roll_board
