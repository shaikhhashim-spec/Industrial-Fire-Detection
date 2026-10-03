"""Bounded weather/FRP prioritization heuristic, not Canadian FWI.

There is no fuel, terrain, soil moisture or accumulated drought state here.
The score is neither a probability nor a forecast of a fire front's movement.
"""
from __future__ import annotations

import math


def calculate_spread_potential(weather: dict, frp_mw: float) -> dict | None:
    """Return optional {score, label, factors, caveat} for current valid weather.

    factors are weighted points (wind 30, dry air 30, heat 15, FRP 25).
    Current precipitation attenuates the total; it is not a drought factor.
    Missing/invalid inputs and stale or synthetic weather yield no score.
    """
    if weather.get("source") in {"offline_fallback", "stale_cache"}:
        return None
    try:
        speed = float(weather["speed_kmh"])
        temperature = float(weather["temperature_c"])
        humidity = float(weather["humidity_pct"])
        rain = float(weather["precipitation_mm"])
        frp = float(frp_mw)
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if not all(math.isfinite(v) for v in (speed, temperature, humidity, rain, frp)):
        return None
    if speed < 0 or rain < 0 or frp < 0 or not 0 <= humidity <= 100 or not -100 <= temperature <= 70:
        return None
    attenuation = 1 / (1 + rain / 2)
    factors = {
        "wind": 30 * min(speed / 60, 1),
        "dryAir": 30 * (1 - humidity / 100),
        "heat": 15 * min(max((temperature - 5) / 35, 0), 1),
        "frp": 25 * min(math.log1p(frp) / math.log1p(100), 1),
    }
    factors = {key: round(value * attenuation, 2) for key, value in factors.items()}
    score = round(min(100, max(0, sum(factors.values()))), 1)
    return {
        "score": score,
        "label": "HIGH" if score >= 70 else "MODERATE" if score >= 40 else "LOW",
        "factors": factors,
        "caveat": "Weather/FRP heuristic, not official FWI or a spread forecast. "
                  "No fuel, terrain or drought history; current precipitation attenuates the score. "
                  "Industrial heat can score highly without a spreading vegetation fire.",
    }
