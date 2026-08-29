import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from src.geospatial.spatial_join import _extract_names, add_industrial_distances


def _flat_zone(name, minx, miny, maxx, maxy):
    return {"name": name, "geometry": box(minx, miny, maxx, maxy)}


def _nested_zone(name, minx, miny, maxx, maxy, extra_tags=None):
    tags = {"name": name}
    if extra_tags:
        tags.update(extra_tags)
    return {"tags": tags, "geometry": box(minx, miny, maxx, maxy)}


def test_extract_names_reads_flat_column():
    zones = gpd.GeoDataFrame([_flat_zone("Tata Steel", 86.10, 22.70, 86.30, 22.90)], crs="EPSG:4326")
    names = _extract_names(zones)
    assert names.iloc[0] == "Tata Steel"


def test_extract_names_reads_nested_tags_dict():
    # This is the real shape osm2geojson produces -- a flat "name" column
    # never exists for live/cached OSM data, only a nested `tags` dict.
    zones = gpd.GeoDataFrame([_nested_zone("Lafarge Cement Warehouse", 86.10, 22.70, 86.30, 22.90)], crs="EPSG:4326")
    names = _extract_names(zones)
    assert names.iloc[0] == "Lafarge Cement Warehouse"


def test_extract_names_missing_name_is_none():
    zones = gpd.GeoDataFrame([{"tags": {"landuse": "industrial"}, "geometry": box(86.10, 22.70, 86.30, 22.90)}],
                              crs="EPSG:4326")
    names = _extract_names(zones)
    assert names.iloc[0] is None


def test_add_industrial_distances_populates_name_from_nested_tags():
    # Regression test: add_industrial_distances() used to only ever check
    # for a flat top-level "name" column, so nearest_industrial_name came
    # back null for every real (osm2geojson-shaped) zone even when it had
    # a perfectly good name tag nested under "tags".
    zones = gpd.GeoDataFrame([_nested_zone("Rourkela Steel Plant", 84.86, 22.24, 84.88, 22.26)], crs="EPSG:4326")
    df = pd.DataFrame({"latitude": [22.25], "longitude": [84.87]})
    out = add_industrial_distances(df, zones)
    assert out.loc[0, "nearest_industrial_name"] == "Rourkela Steel Plant"
    assert out.loc[0, "industrial_distance_km"] == 0.0


def test_add_industrial_distances_still_works_with_flat_name_column():
    zones = gpd.GeoDataFrame([_flat_zone("Demo Zone", 84.86, 22.24, 84.88, 22.26)], crs="EPSG:4326")
    df = pd.DataFrame({"latitude": [22.25], "longitude": [84.87]})
    out = add_industrial_distances(df, zones)
    assert out.loc[0, "nearest_industrial_name"] == "Demo Zone"


def test_add_industrial_distances_no_zones_leaves_name_none():
    df = pd.DataFrame({"latitude": [22.25], "longitude": [84.87]})
    out = add_industrial_distances(df, gpd.GeoDataFrame())
    assert out.loc[0, "nearest_industrial_name"] is None
    assert pd.isna(out.loc[0, "industrial_distance_km"])
