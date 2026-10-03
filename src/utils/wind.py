"""Wind-vector lookup and downwind dispersion-cone geometry, for the
regional map's optional smoke/gas plume overlay on high-intensity hotspots.

Wind data comes from Open-Meteo (open-meteo.com), a free keyless weather
API, with a short on-disk cache (one file per rounded lat/lon so nearby
hotspots share a lookup) and an offline fallback default so a network
hiccup never blocks the map from rendering.

The dispersion cone itself is a simple, clearly-labeled visual heuristic —
cone length scales with wind speed and fire intensity (FRP), direction
points downwind — NOT a Gaussian-plume or other scientific atmospheric
dispersion model. It gives an operator a rough "which way could smoke/gas
be headed" sense, not a regulatory or safety-critical dispersion estimate.
"""
from __future__ import annotations

import json
import math
import time

import requests

import config


def _cache_path(lat: float, lon: float):
    return config.CACHE_DIR / f"wind_{round(lat, 2)}_{round(lon, 2)}.json"


def _finite(value, minimum=None, maximum=None):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number) or (minimum is not None and number < minimum) or (maximum is not None and number > maximum):
        return None
    return number


def _read_cache(cache_file):
    try:
        data = json.loads(cache_file.read_text())
        if not isinstance(data, dict):
            return None
        speed = _finite(data.get("speed_kmh"), 0)
        direction = _finite(data.get("direction_deg"), 0, 360)
        if speed is None or direction is None:
            return None
        return {
            "speed_kmh": speed, "direction_deg": direction % 360,
            "temperature_c": _finite(data.get("temperature_c"), -100, 70),
            "humidity_pct": _finite(data.get("humidity_pct"), 0, 100),
            "precipitation_mm": _finite(data.get("precipitation_mm"), 0),
            "observed_at": data.get("observed_at"),
        }
    except (ValueError, OSError):
        return None


def get_wind(lat: float, lon: float) -> dict:
    """Return wind, temperature_c, humidity_pct, precipitation_mm, observed_at.
    Missing weather values are None; precipitation is the current interval,
    not accumulated drought history. observed_at is the UTC model timestamp.
    direction_deg follows meteorological convention (the direction the
    wind is blowing FROM, 0=N/90=E/180=S/270=W) — use `downwind_bearing()`
    to get the direction smoke actually travels toward. `source` is one of
    "open-meteo", "cache", "stale_cache", or "offline_fallback"."""
    if _finite(lat, -90, 90) is None or _finite(lon, -180, 180) is None:
        raise ValueError("Weather coordinates must be finite WGS84 latitude/longitude")
    cache_file = _cache_path(lat, lon)
    if cache_file.exists():
        age_hours = (time.time() - cache_file.stat().st_mtime) / 3600
        if age_hours < config.WIND_CACHE_TTL_HOURS:
            data = _read_cache(cache_file)
            if data is not None:
                return {**data, "source": "cache"}

    try:
        resp = requests.get(config.OPEN_METEO_URL, params={
            "latitude": lat, "longitude": lon,
            "current": "wind_speed_10m,wind_direction_10m,temperature_2m,relative_humidity_2m,precipitation",
            "wind_speed_unit": "kmh", "temperature_unit": "celsius", "precipitation_unit": "mm",
            "timezone": "GMT",
        }, timeout=8)
        resp.raise_for_status()
        current = resp.json().get("current", {})
        speed = _finite(current.get("wind_speed_10m"), 0)
        direction = _finite(current.get("wind_direction_10m"), 0, 360)
        if speed is None or direction is None:
            raise ValueError("Open-Meteo returned invalid wind")
        result = {
            "speed_kmh": speed, "direction_deg": direction % 360,
            "temperature_c": _finite(current.get("temperature_2m"), -100, 70),
            "humidity_pct": _finite(current.get("relative_humidity_2m"), 0, 100),
            "precipitation_mm": _finite(current.get("precipitation"), 0),
            "observed_at": current.get("time"),
        }
        try:
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(json.dumps(result, allow_nan=False))
        except OSError:
            pass  # Cache storage failure must not discard valid fetched weather.
        return {**result, "source": "open-meteo"}
    except Exception as exc:
        print(f"[utils.wind] Open-Meteo fetch failed, falling back: {exc}")

    if cache_file.exists():
        data = _read_cache(cache_file)
        if data is not None:
            return {**data, "source": "stale_cache"}

    return {"speed_kmh": config.WIND_FALLBACK_SPEED_KMH, "direction_deg": config.WIND_FALLBACK_DIRECTION_DEG,
            "source": "offline_fallback", "temperature_c": None, "humidity_pct": None,
            "precipitation_mm": None, "observed_at": None}


def downwind_bearing(direction_from_deg: float) -> float:
    """The bearing smoke/gas actually travels TOWARD — 180 degrees
    opposite the meteorological "wind FROM" direction."""
    return (direction_from_deg + 180.0) % 360.0


def _project(lat0: float, lon0: float, bearing_deg: float, dist_km: float) -> tuple[float, float]:
    """Destination point `dist_km` along `bearing_deg` from (lat0, lon0),
    via the standard great-circle forward-destination formula."""
    earth_radius_km = 6371.0
    bearing = math.radians(bearing_deg)
    lat1, lon1 = math.radians(lat0), math.radians(lon0)
    d_r = dist_km / earth_radius_km
    lat2 = math.asin(math.sin(lat1) * math.cos(d_r) + math.cos(lat1) * math.sin(d_r) * math.cos(bearing))
    lon2 = lon1 + math.atan2(math.sin(bearing) * math.sin(d_r) * math.cos(lat1),
                              math.cos(d_r) - math.sin(lat1) * math.sin(lat2))
    return math.degrees(lat2), (math.degrees(lon2) + 180) % 360 - 180


def dispersion_cone_length_km(speed_kmh: float, frp_mw: float, min_km: float = 0.5, max_km: float = 8.0) -> float:
    return min(max_km, max(min_km, (speed_kmh / 10.0) * (1.0 + min(frp_mw, 30.0) / 15.0)))


def dispersion_cone_polygon(
    lat: float, lon: float, direction_from_deg: float, speed_kmh: float, frp_mw: float,
    cone_half_angle_deg: float = 25.0,
) -> list[tuple[float, float]]:
    """A polygon (list of (lat, lon), apex-first) approximating a downwind
    dispersion hazard cone from a hotspot at (lat, lon). See module
    docstring — this is a visual heuristic, not a physics-based model."""
    bearing = downwind_bearing(direction_from_deg)
    length_km = dispersion_cone_length_km(speed_kmh, frp_mw)
    apex = (lat, lon)
    # A handful of points across the cone's angular span give the far edge
    # a gentle arc rather than a sharp two-straight-edges triangle.
    arc_points = [
        _project(lat, lon, bearing - cone_half_angle_deg + cone_half_angle_deg * 2 * t / 6, length_km)
        for t in range(7)
    ]
    return [apex] + arc_points + [apex]
