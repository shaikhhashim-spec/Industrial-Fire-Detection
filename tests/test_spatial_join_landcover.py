import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from src.geospatial.spatial_join import join_landcover_context


def _zone(kind_tag_key, kind_tag_value, minx, miny, maxx, maxy):
    return {"tags": {kind_tag_key: kind_tag_value}, "geometry": box(minx, miny, maxx, maxy)}


def test_empty_landcover_leaves_defaults():
    df = pd.DataFrame({"latitude": [22.8], "longitude": [86.18]})
    out = join_landcover_context(df, gpd.GeoDataFrame())
    assert out.loc[0, "in_agricultural_zone"] == False  # noqa: E712
    assert pd.isna(out.loc[0, "forest_distance_km"])
    assert pd.isna(out.loc[0, "water_distance_km"])


def test_point_inside_farmland_is_agricultural():
    zones = gpd.GeoDataFrame(
        [_zone("landuse", "farmland", 86.10, 22.70, 86.30, 22.90)], crs="EPSG:4326"
    )
    df = pd.DataFrame({"latitude": [22.80], "longitude": [86.20]})
    out = join_landcover_context(df, zones)
    assert bool(out.loc[0, "in_agricultural_zone"])


def test_point_near_forest_gets_short_distance():
    zones = gpd.GeoDataFrame(
        [_zone("natural", "wood", 86.20, 22.80, 86.25, 22.85)], crs="EPSG:4326"
    )
    df = pd.DataFrame({"latitude": [22.80], "longitude": [86.19]})  # just west of the forest box
    out = join_landcover_context(df, zones)
    assert out.loc[0, "forest_distance_km"] < 5.0


def test_point_far_from_water_gets_large_distance():
    zones = gpd.GeoDataFrame(
        [_zone("natural", "water", 88.0, 25.0, 88.1, 25.1)], crs="EPSG:4326"
    )
    df = pd.DataFrame({"latitude": [22.80], "longitude": [86.18]})
    out = join_landcover_context(df, zones)
    assert out.loc[0, "water_distance_km"] > 100.0
