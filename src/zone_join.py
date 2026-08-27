"""Spatially join hotspots against OSM industrial/mining polygons to tag
each one as being inside (or near) an industrial zone."""
from __future__ import annotations

import geopandas as gpd
import pandas as pd

import config


def join_zone_type(df: pd.DataFrame, industrial_zones: gpd.GeoDataFrame) -> pd.DataFrame:
    """Add a `zone_type` column: "industrial" or "other".

    Polygons (and buffered points) from OSM are buffered by
    config.INDUSTRIAL_BUFFER_M in a metric CRS before the join, so a hotspot
    just outside a mapped plant boundary still counts as industrial.
    """
    df = df.copy()
    df["zone_type"] = "other"

    if industrial_zones is None or industrial_zones.empty:
        return df

    points = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["longitude"], df["latitude"]),
        crs="EPSG:4326",
    )

    zones_m = industrial_zones.to_crs(config.UTM_CRS)
    zones_m["geometry"] = zones_m.geometry.buffer(config.INDUSTRIAL_BUFFER_M)
    zones_m = zones_m.dissolve()[["geometry"]]
    zones_wgs = zones_m.to_crs("EPSG:4326")

    joined = gpd.sjoin(points, zones_wgs, how="left", predicate="within")
    df["zone_type"] = joined["index_right"].notna().map({True: "industrial", False: "other"}).values
    return df
