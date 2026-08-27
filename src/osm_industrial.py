"""Pull industrial-zone / mining polygons from OpenStreetMap via Overpass."""
from __future__ import annotations

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
);
out body;
>;
out skel qt;
"""


class OsmFetchError(RuntimeError):
    pass


def fetch_industrial_zones() -> gpd.GeoDataFrame:
    """Query Overpass for industrial/mining polygons in the target bbox.

    Raises OsmFetchError on network/parse failure; caller should fall back
    to the cached copy or synthetic sample zones.
    """
    query = QUERY_TEMPLATE.format(timeout=config.OVERPASS_TIMEOUT, bbox=config.OVERPASS_BBOX_STR)
    headers = {"User-Agent": "SIH26162-thermal-source-detector/1.0 (contact: khotabdurrahman@eng.rizvi.edu.in)"}
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


def load_cached_industrial_zones() -> gpd.GeoDataFrame | None:
    if config.OSM_CACHE_PATH.exists():
        return gpd.read_file(config.OSM_CACHE_PATH)
    return None


def get_industrial_zones(use_cache_first: bool = False) -> tuple[gpd.GeoDataFrame, str]:
    """Return (gdf, source_label). Tries live Overpass, then cache, then
    synthetic sample zones so the pipeline always has something to join
    against."""
    from src import sample_data  # local import avoids a hard circular dep

    if use_cache_first:
        cached = load_cached_industrial_zones()
        if cached is not None and not cached.empty:
            return cached, "cache"

    try:
        gdf = fetch_industrial_zones()
        if not gdf.empty:
            return gdf, "overpass_live"
    except OsmFetchError as exc:
        print(f"[osm_industrial] {exc}")

    cached = load_cached_industrial_zones()
    if cached is not None and not cached.empty:
        return cached, "cache"

    print("[osm_industrial] falling back to synthetic sample industrial zones")
    return sample_data.generate_sample_industrial_zones(), "sample"


if __name__ == "__main__":
    zones, src = get_industrial_zones()
    print(f"Loaded {len(zones)} industrial zones from {src}")
