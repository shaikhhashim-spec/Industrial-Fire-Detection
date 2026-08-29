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


def get_wind(lat: float, lon: float) -> dict:
    """Returns {"speed_kmh": float, "direction_deg": float, "source": str}.
    direction_deg follows meteorological convention (the direction the
    wind is blowing FROM, 0=N/90=E/180=S/270=W) — use `downwind_bearing()`
    to get the direction smoke actually travels toward. `source` is one of
    "open-meteo", "cache", "stale_cache", or "offline_fallback"."""
    cache_file = _cache_path(lat, lon)
    if cache_file.exists():
        age_hours = (time.time() - cache_file.stat().st_mtime) / 3600
        if age_hours < config.WIND_CACHE_TTL_HOURS:
            try:
                data = json.loads(cache_file.read_text())
                return {**data, "source": "cache"}
            except (json.JSONDecodeError, OSError, KeyError):
                pass

    try:
        resp = requests.get(config.OPEN_METEO_URL, params={
            "latitude": lat, "longitude": lon,
            "current": "wind_speed_10m,wind_direction_10m", "wind_speed_unit": "kmh",
        }, timeout=8)
        resp.raise_for_status()
        current = resp.json().get("current", {})
        result = {"speed_kmh": float(current["wind_speed_10m"]), "direction_deg": float(current["wind_direction_10m"])}
        cache_file.write_text(json.dumps(result))
        return {**result, "source": "open-meteo"}
    except Exception as exc:
        print(f"[utils.wind] Open-Meteo fetch failed, falling back: {exc}")

    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text())
            return {**data, "source": "stale_cache"}
        except (json.JSONDecodeError, OSError, KeyError):
            pass

    return {"speed_kmh": config.WIND_FALLBACK_SPEED_KMH, "direction_deg": config.WIND_FALLBACK_DIRECTION_DEG,
            "source": "offline_fallback"}


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
    return math.degrees(lat2), math.degrees(lon2)


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
