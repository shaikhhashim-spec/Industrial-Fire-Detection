"""Color-math utilities: hex/RGB conversion and WCAG contrast-ratio
helpers. Used to keep the dashboard's status/risk/category badge colors
readable in both its dark and light themes — several of the palette's
bright accent colors (tuned to read well against a near-black dark-mode
background) fall short of WCAG AA text contrast against a white or
near-white light-mode background.
"""
from __future__ import annotations

import colorsys
import functools

WCAG_AA_NORMAL_TEXT = 4.5


def hex_to_rgb01(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return r, g, b


def rgb01_to_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(max(0.0, min(1.0, c)) * 255):02x}" for c in rgb)


def relative_luminance(rgb: tuple[float, float, float]) -> float:
    def lin(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(rgb_a: tuple[float, float, float], rgb_b: tuple[float, float, float]) -> float:
    la, lb = relative_luminance(rgb_a), relative_luminance(rgb_b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


@functools.lru_cache(maxsize=256)
def darken_for_contrast(hex_color: str, background_hex: str, min_ratio: float = WCAG_AA_NORMAL_TEXT) -> str:
    """Returns `hex_color` unchanged if it already meets `min_ratio`
    contrast against `background_hex`. Otherwise walks its HSL lightness
    down — same hue, a deeper tone, never a different color — until it
    does, rather than guessing a fixed clamp value that might not hold for
    every hue. Bottoms out at black in the (currently unreached, since the
    real palette never needs it) case a color can't reach the target
    ratio at all."""
    rgb = hex_to_rgb01(hex_color)
    bg = hex_to_rgb01(background_hex)
    if contrast_ratio(rgb, bg) >= min_ratio:
        return hex_color
    h, l, s = colorsys.rgb_to_hls(*rgb)
    for _ in range(40):
        if contrast_ratio(colorsys.hls_to_rgb(h, l, s), bg) >= min_ratio or l <= 0.0:
            break
        l = max(0.0, l - 0.02)
    return rgb01_to_hex(colorsys.hls_to_rgb(h, l, s))
