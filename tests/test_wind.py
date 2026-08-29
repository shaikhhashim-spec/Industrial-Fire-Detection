import math

import pytest

from src.utils import wind


def test_downwind_bearing_is_opposite():
    assert wind.downwind_bearing(0) == 180
    assert wind.downwind_bearing(270) == 90
    assert wind.downwind_bearing(90) == 270
    assert wind.downwind_bearing(350) == 170


def test_get_wind_offline_fallback_when_network_unavailable(monkeypatch, tmp_path):
    monkeypatch.setattr(wind.config, "CACHE_DIR", tmp_path)

    def _raise(*a, **k):
        raise ConnectionError("no network in test")
    monkeypatch.setattr(wind.requests, "get", _raise)

    result = wind.get_wind(23.0, 85.0)
    assert result["source"] == "offline_fallback"
    assert result["speed_kmh"] == wind.config.WIND_FALLBACK_SPEED_KMH
    assert result["direction_deg"] == wind.config.WIND_FALLBACK_DIRECTION_DEG


def test_get_wind_uses_fresh_cache_without_network_call(monkeypatch, tmp_path):
    monkeypatch.setattr(wind.config, "CACHE_DIR", tmp_path)
    cache_file = wind._cache_path(23.0, 85.0)
    cache_file.write_text('{"speed_kmh": 20.0, "direction_deg": 45.0}')

    def _fail_if_called(*a, **k):
        raise AssertionError("should not hit the network when cache is fresh")
    monkeypatch.setattr(wind.requests, "get", _fail_if_called)

    result = wind.get_wind(23.0, 85.0)
    assert result["source"] == "cache"
    assert result["speed_kmh"] == 20.0
    assert result["direction_deg"] == 45.0


def test_dispersion_cone_length_scales_with_speed_and_frp():
    low = wind.dispersion_cone_length_km(speed_kmh=5.0, frp_mw=1.0)
    high = wind.dispersion_cone_length_km(speed_kmh=40.0, frp_mw=25.0)
    assert low < high
    assert wind.dispersion_cone_length_km(0, 0) >= 0.5  # never below min_km
    assert wind.dispersion_cone_length_km(1000, 1000) <= 8.0  # never above max_km


def test_dispersion_cone_polygon_points_downwind():
    # Wind FROM the north (0 deg) -> smoke travels toward the south (bearing 180)
    # -> polygon points should all end up south of the apex (lower latitude).
    poly = wind.dispersion_cone_polygon(lat=23.0, lon=85.0, direction_from_deg=0.0, speed_kmh=20.0, frp_mw=10.0)
    apex = poly[0]
    assert apex == (23.0, 85.0)
    assert len(poly) == 9  # apex + 7 arc points + apex (closes the ring)
    for lat, lon in poly[1:-1]:
        assert lat < 23.0  # south of the apex


def test_dispersion_cone_polygon_closes_the_ring():
    poly = wind.dispersion_cone_polygon(lat=23.0, lon=85.0, direction_from_deg=90.0, speed_kmh=15.0, frp_mw=8.0)
    assert poly[0] == poly[-1]


def test_project_roundtrip_distance_is_approximately_correct():
    lat2, lon2 = wind._project(0.0, 0.0, bearing_deg=90.0, dist_km=111.19)  # ~1 degree of longitude at equator
    assert lat2 == pytest.approx(0.0, abs=0.01)
    assert lon2 == pytest.approx(1.0, abs=0.05)
