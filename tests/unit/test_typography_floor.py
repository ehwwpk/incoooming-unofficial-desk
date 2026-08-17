from __future__ import annotations

import re
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parents[2] / "src" / "schwab_dashboard" / "web" / "static"

ART_ONLY_STYLESHEETS = {"nibwick-promenade.css", "sources-art.css"}
ART_ONLY_SELECTORS = {".nibwick-obstacle", ".nibwick pre"}
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
