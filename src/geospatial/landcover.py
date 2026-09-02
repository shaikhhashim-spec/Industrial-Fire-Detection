"""Pull forest, water-body, and agricultural-land polygons from OpenStreetMap
via Overpass — a separate query/cache from src/geospatial/osm.py's
industrial/mining/power pull, deliberately kept independent so that:

1. A failure here (landcover polygons, especially forest/farmland, can be
   huge over a multi-degree bbox and are more likely to make Overpass time
   out) never breaks the already-reliable industrial-zone join.
2. Landcover context is genuinely optional enrichment — the rule engine's
   existing burn-season-month approximation for wildfire/agricultural-burn
   classification (see src/ml/rules.py) is the safe fallback when this data
   is unavailable, not a synthetic placeholder pretending to be real land
   cover.
"""
from __future__ import annotations

import time

import geopandas as gpd
import osm2geojson
import requests

import config

QUERY_TEMPLATE = """
[out:json][timeout:{timeout}];
(
  way["natural"="wood"]({bbox});
  relation["natural"="wood"]({bbox});
  way["landuse"="forest"]({bbox});
  relation["landuse"="forest"]({bbox});
  way["natural"="water"]({bbox});
  relation["natural"="water"]({bbox});
  way["landuse"="reservoir"]({bbox});
  way["landuse"="farmland"]({bbox});
  way["landuse"="orchard"]({bbox});
);
out body;
>;
out skel qt;
"""


class LandcoverFetchError(RuntimeError):
    pass


def fetch_landcover_zones() -> gpd.GeoDataFrame:
    query = QUERY_TEMPLATE.format(timeout=config.OVERPASS_TIMEOUT, bbox=config.OVERPASS_BBOX_STR)
    headers = {"User-Agent": "SIH26162-thermal-source-detector/1.0"}
    try:
        resp = requests.post(
            config.OVERPASS_URL, data={"data": query}, headers=headers, timeout=config.OVERPASS_TIMEOUT + 10
        )
        resp.raise_for_status()
        overpass_json = resp.json()
    except Exception as exc:
        raise LandcoverFetchError(f"Overpass landcover query failed: {exc}") from exc

    geojson = osm2geojson.json2geojson(overpass_json)
    gdf = gpd.GeoDataFrame.from_features(geojson["features"], crs="EPSG:4326")
    gdf = gdf[gdf.geometry.type.isin(["Polygon", "MultiPolygon"])].reset_index(drop=True)

    if not gdf.empty:
        config.LANDCOVER_CACHE_PATH.write_text(gdf.to_json())
    return gdf


def _cache_is_fresh() -> bool:
    if not config.LANDCOVER_CACHE_PATH.exists():
        return False
    age_hours = (time.time() - config.LANDCOVER_CACHE_PATH.stat().st_mtime) / 3600
    return age_hours < config.OVERPASS_CACHE_TTL_HOURS


def load_cached_landcover_zones() -> gpd.GeoDataFrame | None:
    if config.LANDCOVER_CACHE_PATH.exists():
        from src.utils.geo_io import read_geojson
        try:
            return read_geojson(config.LANDCOVER_CACHE_PATH)
        except Exception as e:
            print(f"[geospatial.landcover] failed to read cache: {e}")
            return None
    return None


def get_landcover_zones(use_cache_first: bool = False) -> tuple[gpd.GeoDataFrame, str]:
    """Return (gdf, source_label). Unlike the industrial-zone equivalent,
    the last resort here is an EMPTY frame + "unavailable", never synthetic
    forest/water polygons — rules.py degrades gracefully to its existing
    burn-season-month approximation when this returns empty."""
    if use_cache_first or _cache_is_fresh():
        cached = load_cached_landcover_zones()
        if cached is not None and not cached.empty:
            return cached, "cache"

    try:
        gdf = fetch_landcover_zones()
        if not gdf.empty:
            return gdf, "overpass_live"
    except LandcoverFetchError as exc:
        print(f"[geospatial.landcover] {exc}")

    cached = load_cached_landcover_zones()
    if cached is not None and not cached.empty:
        return cached, "cache_stale"

    print("[geospatial.landcover] no landcover data available — rule engine falls back to burn-season-month approximation")
    return gpd.GeoDataFrame(), "unavailable"


if __name__ == "__main__":
    zones, src = get_landcover_zones()
    print(f"Loaded {len(zones)} landcover zones from {src}")
