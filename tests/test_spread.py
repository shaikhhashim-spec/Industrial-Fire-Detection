import math

import pytest

from src.utils.spread import calculate_spread_potential


def weather(**changes):
    return dict(speed_kmh=30, temperature_c=30, humidity_pct=35,
                precipitation_mm=0, source="open-meteo", **changes)


def test_bounded_extremes_and_factor_sum():
    result = calculate_spread_potential(
        {"speed_kmh": 1000, "temperature_c": 70, "humidity_pct": 0, "precipitation_mm": 0}, 10000)
    assert result["score"] == 100
    assert result["label"] == "HIGH"
    assert sum(result["factors"].values()) == 100
    assert "not official FWI" in result["caveat"]


def test_rain_attenuates_and_wind_increases_score():
    dry = weather()
    rain = {**dry, "precipitation_mm": 8}
    windy = {**dry, "speed_kmh": 60}
    assert calculate_spread_potential(rain, 20)["score"] < calculate_spread_potential(dry, 20)["score"]
    assert calculate_spread_potential(windy, 20)["score"] > calculate_spread_potential(dry, 20)["score"]


@pytest.mark.parametrize("field,value", [("humidity_pct", None), ("humidity_pct", 101),
    ("speed_kmh", -1), ("temperature_c", math.nan), ("precipitation_mm", -1),
    ("source", "offline_fallback"), ("source", "stale_cache")])
def test_missing_or_invalid_weather_has_no_score(field, value):
    assert calculate_spread_potential({**weather(), field: value}, 20) is None


@pytest.mark.parametrize("frp", [-1, math.nan, math.inf, None])
def test_invalid_frp_has_no_score(frp):
    assert calculate_spread_potential(weather(), frp) is None
