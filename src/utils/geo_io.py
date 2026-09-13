"""Robust GeoJSON reader and writer that does not depend on GDAL, pyogrio, or fiona C-bindings."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import geopandas as gpd


def read_geojson(path: str | Path, default_crs: str = "EPSG:4326") -> gpd.GeoDataFrame:
    """Read a GeoJSON file into a GeoDataFrame using pure Python json parsing."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"GeoJSON file not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        crs = data.get("crs", {}).get("properties", {}).get("name", default_crs)
        features = data.get("features", [])
        return gpd.GeoDataFrame.from_features(features, crs=crs)
    elif isinstance(data, list):
        return gpd.GeoDataFrame.from_features(data, crs=default_crs)
    return gpd.GeoDataFrame(crs=default_crs)


def write_geojson(gdf: gpd.GeoDataFrame, path: str | Path) -> None:
    """Write a GeoDataFrame to a GeoJSON file using pure GeoPandas JSON serialization."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    json_str = gdf.to_json(default=str)
    path.write_text(json_str, encoding="utf-8")
