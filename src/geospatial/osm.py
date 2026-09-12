"""Pull industrial-zone / mining polygons from OpenStreetMap via Overpass,
with a TTL cache so repeated dashboard interactions don't re-query Overpass
on every run."""
from __future__ import annotations

import time

import geopandas as gpd
import osm2geojson
import requests

import config

QUERY_TEMPLATE = """
[out:json][timeout:{timeout}];
(
  way["landuse"="industrial"]({bbox});
  relation["landuse"="industrial"]({bbox});
  way["landuse"="quarry"]({bbox});
  way["man_made"="works"]({bbox});
  node["man_made"="works"]({bbox});
  way["industrial"]({bbox});
  way["man_made"="mineshaft"]({bbox});
  node["man_made"="mineshaft"]({bbox});
  way["power"="plant"]({bbox});
  node["power"="plant"]({bbox});
);
out body;
>;
out skel qt;
"""


class OsmFetchError(RuntimeError):
    pass


def fetch_industrial_zones() -> gpd.GeoDataFrame:
    """Query Overpass for industrial/mining/power polygons in the target bbox.
    Raises OsmFetchError on network/parse failure; caller should fall back
    to the cached copy or synthetic sample zones (see the fallback hierarchy
    in src/pipeline.py)."""
    query = QUERY_TEMPLATE.format(timeout=config.OVERPASS_TIMEOUT, bbox=config.OVERPASS_BBOX_STR)
    headers = {"User-Agent": "SIH26162-thermal-source-detector/1.0"}
    try:
        resp = requests.post(
            config.OVERPASS_URL, data={"data": query}, headers=headers, timeout=config.OVERPASS_TIMEOUT + 10
        )
        resp.raise_for_status()
        overpass_json = resp.json()
    except Exception as exc:
        raise OsmFetchError(f"Overpass query failed: {exc}") from exc

    geojson = osm2geojson.json2geojson(overpass_json)
    gdf = gpd.GeoDataFrame.from_features(geojson["features"], crs="EPSG:4326")
    gdf = gdf[gdf.geometry.type.isin(["Polygon", "MultiPolygon", "Point"])].reset_index(drop=True)

    if not gdf.empty:
        config.OSM_CACHE_PATH.write_text(gdf.to_json())
    return gdf


def _cache_is_fresh() -> bool:
    if not config.OSM_CACHE_PATH.exists():
        return False
    age_hours = (time.time() - config.OSM_CACHE_PATH.stat().st_mtime) / 3600
    return age_hours < config.OVERPASS_CACHE_TTL_HOURS


def load_cached_industrial_zones() -> gpd.GeoDataFrame | None:
    if config.OSM_CACHE_PATH.exists():
        return gpd.read_file(config.OSM_CACHE_PATH)
    return None


def get_industrial_zones(use_cache_first: bool = False) -> tuple[gpd.GeoDataFrame, str]:
    """Return (gdf, source_label). Tries a fresh cache, then live Overpass,
    then a stale cache of a previous real pull. Never synthetic: with nothing
    real available it returns an empty frame labelled "unavailable", and every
    detection simply joins as outside any mapped zone."""
    if use_cache_first or _cache_is_fresh():
        cached = load_cached_industrial_zones()
        if cached is not None and not cached.empty:
            return cached, "cache"

    try:
        gdf = fetch_industrial_zones()
        if not gdf.empty:
            return gdf, "overpass_live"
    except OsmFetchError as exc:
        print(f"[geospatial.osm] {exc}")

    cached = load_cached_industrial_zones()
    if cached is not None and not cached.empty:
        return cached, "cache_stale"

    print("[geospatial.osm] no real industrial-zone data available")
    return gpd.GeoDataFrame({"zone_type": [], "name": []}, geometry=[], crs="EPSG:4326"), "unavailable"


if __name__ == "__main__":
    zones, src = get_industrial_zones()
    print(f"Loaded {len(zones)} industrial zones from {src}")
