import pytest

from src.utils.color import (
    contrast_ratio,
    darken_for_contrast,
    hex_to_rgb01,
    relative_luminance,
    rgb01_to_hex,
)

# The dashboard's real CATEGORY_COLORS / RISK_COLORS / STATUS_COLORS
# "Cyber-Slate" palette (app.py) — kept as a literal copy rather than
# importing app.py, since the rest of this test suite deliberately never
# imports app.py (a Streamlit script with import-time side effects like
# st.set_page_config); the project's own convention verifies app.py itself
# via AppTest instead.
PALETTE = [
    "#3b82f6", "#f97316", "#10b981", "#f59e0b", "#8b5cf6", "#16a34a", "#06b6d4", "#ef4444",
    "#94a3b8", "#64748b",
]
LIGHT_PAGE_BG = "#f5f6f8"
LIGHT_SURFACE_BG = "#ffffff"
DARK_PAGE_BG = "#0b0f19"


def test_hex_rgb_roundtrip():
    for h in ["#000000", "#ffffff", "#4d8fc4", "#fab219"]:
        assert rgb01_to_hex(hex_to_rgb01(h)) == h


def test_contrast_ratio_black_on_white_is_max():
    assert contrast_ratio(hex_to_rgb01("#000000"), hex_to_rgb01("#ffffff")) == pytest.approx(21.0, abs=0.01)


def test_contrast_ratio_identical_colors_is_one():
    assert contrast_ratio(hex_to_rgb01("#4d8fc4"), hex_to_rgb01("#4d8fc4")) == pytest.approx(1.0, abs=0.01)


def test_contrast_ratio_symmetric():
    a, b = hex_to_rgb01("#4d8fc4"), hex_to_rgb01("#ffffff")
    assert contrast_ratio(a, b) == pytest.approx(contrast_ratio(b, a), abs=1e-9)


def test_relative_luminance_white_is_one_black_is_zero():
    assert relative_luminance(hex_to_rgb01("#ffffff")) == pytest.approx(1.0, abs=0.01)
    assert relative_luminance(hex_to_rgb01("#000000")) == pytest.approx(0.0, abs=0.01)


def test_darken_for_contrast_leaves_already_safe_colors_unchanged():
    # Near-black is already far above 4.5:1 against white — nothing to darken.
    assert darken_for_contrast("#111111", "#ffffff") == "#111111"


def test_darken_for_contrast_preserves_hue_family():
    # Darkening #fab219 (amber) shouldn't turn it into an unrelated hue —
    # its hue angle should stay roughly put even as lightness drops.
    import colorsys
    orig_h, _, _ = colorsys.rgb_to_hls(*hex_to_rgb01("#fab219"))
    darkened = darken_for_contrast("#fab219", "#f5f6f8")
    new_h, _, _ = colorsys.rgb_to_hls(*hex_to_rgb01(darkened))
    assert abs(orig_h - new_h) < 0.02


@pytest.mark.parametrize("color", PALETTE)
@pytest.mark.parametrize("bg", [LIGHT_PAGE_BG, LIGHT_SURFACE_BG])
def test_every_palette_color_meets_wcag_aa_on_light_backgrounds(color, bg):
    safe = darken_for_contrast(color, LIGHT_PAGE_BG)  # app.py always targets the stricter page bg
    ratio = contrast_ratio(hex_to_rgb01(safe), hex_to_rgb01(bg))
    assert ratio >= 4.5, f"{color} -> {safe} only reaches {ratio:.2f}:1 against {bg}"


@pytest.mark.parametrize("color", PALETTE)
def test_dark_mode_colors_still_read_fine_against_dark_page(color):
    # Sanity check that the ORIGINAL (undarkened) palette — what dark mode
    # actually uses — already had reasonable contrast against the dark
    # background; this isn't a strict AA requirement (small UI accents are
    # commonly exempt), just confirms dark mode was never the problem.
    ratio = contrast_ratio(hex_to_rgb01(color), hex_to_rgb01(DARK_PAGE_BG))
    assert ratio >= 3.0
