"""India state boundaries — a real published dataset (GADM-derived), not a
hand-drawn approximation. Used only for a coarse point-in-polygon state tag
and rendering state outlines on the national map; this is a cheap spatial
join against ~36 polygons, not the expensive per-hotspot industrial OSM join
that only runs for the detailed Jharkhand–Odisha region.
"""
from __future__ import annotations

import geopandas as gpd
import pandas as pd

import config

from src.utils.geo_io import read_geojson

_cache: gpd.GeoDataFrame | None = None


def load_states() -> gpd.GeoDataFrame:
    global _cache
    if _cache is not None:
        return _cache
    gdf = read_geojson(config.INDIA_STATES_PATH)
    if gdf.crs is not None and str(gdf.crs).upper() != "EPSG:4326":
        gdf = gdf.to_crs("EPSG:4326")
    gdf["state_name"] = gdf["state_name"].replace(config.STATE_NAME_ALIASES)
    _cache = gdf
    return gdf


def assign_state(df: pd.DataFrame) -> pd.DataFrame:
    """Add a `state` column via point-in-polygon against real state
    boundaries. Points outside any mapped state (offshore detections, etc.)
    get `None`."""
    df = df.copy()
    if df.empty:
        df["state"] = pd.Series(dtype="object")
        return df

    states = load_states()
    points = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["longitude"], df["latitude"]), crs="EPSG:4326")
    joined = gpd.sjoin(points, states[["state_name", "geometry"]], how="left", predicate="within")
    joined = joined[~joined.index.duplicated(keep="first")]
    df["state"] = joined["state_name"].values
    return df
