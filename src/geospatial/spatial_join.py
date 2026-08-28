"""Spatially join hotspots against OSM industrial/mining polygons: whether
each one falls inside a zone, and its distance to the nearest industrial
area and to the nearest mine specifically."""
from __future__ import annotations

import geopandas as gpd
import pandas as pd

import config


def _points_gdf(df: pd.DataFrame) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df["longitude"], df["latitude"]), crs="EPSG:4326")


def _classify_zone_kind(zones: gpd.GeoDataFrame) -> pd.Series:
    """Best-effort tag-based split into 'mine' / 'power' / 'industrial'
    (general), since OSM's own tag vocabulary doesn't cleanly separate
    "factory" from generic landuse=industrial.

    osm2geojson nests OSM tags under a single `tags` dict column rather than
    flattening them to top-level columns — the tag lookup below reads both
    that nested dict AND any flat top-level columns, so it works regardless
    of which shape a given Overpass/osm2geojson conversion produces."""
    def _kind(row):
        tags = {}
        nested = row.get("tags")
        if isinstance(nested, dict):
            tags.update({str(k).lower(): str(v).lower() for k, v in nested.items() if v is not None})
        for k, v in row.items():
            if k in ("geometry", "tags") or isinstance(v, (list, dict, tuple)):
                continue
            try:
                if pd.isna(v):
                    continue
            except (TypeError, ValueError):
                continue
            tags[str(k).lower()] = str(v).lower()
        if tags.get("landuse") == "quarry" or tags.get("man_made") == "mineshaft":
            return "mine"
        if tags.get("power") == "plant":
            return "power"
        return "industrial"
    return zones.apply(_kind, axis=1)


def join_zone_type(df: pd.DataFrame, industrial_zones: gpd.GeoDataFrame) -> pd.DataFrame:
    """Add `zone_type` ("industrial" or "other") — inside a buffered
    industrial/mining polygon or not. This exact binary field is a
    dependency of the rule engine, ML features, and risk scoring, so its
    semantics are left untouched here; the finer-grained `zone_kind`
    ("mine" / "power" / "industrial" / "other" — evidence/context only,
    not used by classification or scoring) is added alongside it, not in
    place of it."""
    df = df.copy()
    df["zone_type"] = "other"
    df["zone_kind"] = "other"
    if industrial_zones is None or industrial_zones.empty:
        return df

    points = _points_gdf(df)
    zones_m = industrial_zones.to_crs(config.UTM_CRS).copy()
    zones_m["geometry"] = zones_m.geometry.buffer(config.INDUSTRIAL_BUFFER_M)
    zones_m["_kind"] = _classify_zone_kind(industrial_zones)

    dissolved = zones_m.dissolve()[["geometry"]].to_crs("EPSG:4326")
    joined = gpd.sjoin(points, dissolved, how="left", predicate="within")
    df["zone_type"] = joined["index_right"].notna().map({True: "industrial", False: "other"}).values

    # Priority if a point falls in overlapping zones of different kinds:
    # mine > power > industrial (mine/power tags are the more specific of
    # the two, so they take precedence over the generic industrial bucket).
    for kind in ("industrial", "power", "mine"):
        subset = zones_m[zones_m["_kind"] == kind][["geometry"]]
        if subset.empty:
            continue
        subset_wgs = subset.dissolve()[["geometry"]].to_crs("EPSG:4326")
        hit = gpd.sjoin(points, subset_wgs, how="left", predicate="within")["index_right"].notna().values
        df.loc[hit, "zone_kind"] = kind
    return df


def add_industrial_distances(df: pd.DataFrame, industrial_zones: gpd.GeoDataFrame) -> pd.DataFrame:
    """Add `industrial_distance_km` (nearest industrial/mining/power feature,
    0 if inside one) and `mine_distance_km` (nearest quarry/mineshaft
    specifically). Vectorized via GeoPandas' spatial index for performance
    at thousands of points."""
    df = df.copy()
    df["industrial_distance_km"] = float("nan")
    df["mine_distance_km"] = float("nan")
    df["power_distance_km"] = float("nan")
    df["nearest_industrial_name"] = None
    if industrial_zones is None or industrial_zones.empty or df.empty:
        return df

    points_m = _points_gdf(df).to_crs(config.UTM_CRS)
    zones_m = industrial_zones.to_crs(config.UTM_CRS).copy()
    zones_m["_kind"] = _classify_zone_kind(industrial_zones)
    name_col = "name" if "name" in zones_m.columns else None

    def _nearest(zone_subset: gpd.GeoDataFrame) -> tuple[pd.Series, pd.Series]:
        if zone_subset.empty:
            return pd.Series([float("nan")] * len(points_m)), pd.Series([None] * len(points_m))
        nearest = gpd.sjoin_nearest(points_m, zone_subset[["geometry"] + ([name_col] if name_col else [])],
                                     how="left", distance_col="_dist_m")
        nearest = nearest[~nearest.index.duplicated(keep="first")]
        dist_km = (nearest["_dist_m"] / 1000).round(3)
        names = nearest[name_col] if name_col else pd.Series([None] * len(nearest), index=nearest.index)
        return dist_km, names

    industrial_dist, industrial_names = _nearest(zones_m)
    df["industrial_distance_km"] = industrial_dist.values
    df["nearest_industrial_name"] = industrial_names.values

    mines = zones_m[zones_m["_kind"] == "mine"]
    mine_dist, _ = _nearest(mines)
    df["mine_distance_km"] = mine_dist.values

    power = zones_m[zones_m["_kind"] == "power"]
    power_dist, _ = _nearest(power)
    df["power_distance_km"] = power_dist.values

    return df


def _classify_landcover_kind(zones: gpd.GeoDataFrame) -> pd.Series:
    """Tag-based split into 'forest' / 'water' / 'agricultural' for the
    src/geospatial/landcover.py Overpass pull. Same nested-`tags`-dict
    reading as _classify_zone_kind (see its docstring for why)."""
    def _kind(row):
        tags = {}
        nested = row.get("tags")
        if isinstance(nested, dict):
            tags.update({str(k).lower(): str(v).lower() for k, v in nested.items() if v is not None})
        for k, v in row.items():
            if k in ("geometry", "tags") or isinstance(v, (list, dict, tuple)):
                continue
            try:
                if pd.isna(v):
                    continue
            except (TypeError, ValueError):
                continue
            tags[str(k).lower()] = str(v).lower()
        if tags.get("natural") == "water" or tags.get("landuse") == "reservoir":
            return "water"
        if tags.get("landuse") in ("farmland", "orchard"):
            return "agricultural"
        if tags.get("natural") == "wood" or tags.get("landuse") == "forest":
            return "forest"
        return "other"
    return zones.apply(_kind, axis=1)


def join_landcover_context(df: pd.DataFrame, landcover_zones: gpd.GeoDataFrame) -> pd.DataFrame:
    """Add `forest_distance_km`, `water_distance_km` (nearest feature of
    each kind, 0 if inside/on one) and `in_agricultural_zone` (boolean,
    inside a buffered farmland/orchard polygon) — real OSM-polygon-backed
    replacements for what the rule engine previously had to approximate
    purely from burn-season month. Independent of the industrial-zone join;
    an empty/missing `landcover_zones` (Overpass unavailable) just leaves
    these as NaN/False, and src/ml/rules.py falls back to its existing
    burn-season-month approximation in that case — never a crash."""
    df = df.copy()
    df["forest_distance_km"] = float("nan")
    df["water_distance_km"] = float("nan")
    df["in_agricultural_zone"] = False
    if landcover_zones is None or landcover_zones.empty or df.empty:
        return df

    points_m = _points_gdf(df).to_crs(config.UTM_CRS)
    zones_m = landcover_zones.to_crs(config.UTM_CRS).copy()
    zones_m["_kind"] = _classify_landcover_kind(landcover_zones)

    def _nearest_km(zone_subset: gpd.GeoDataFrame) -> pd.Series:
        if zone_subset.empty:
            return pd.Series([float("nan")] * len(points_m))
        nearest = gpd.sjoin_nearest(points_m, zone_subset[["geometry"]], how="left", distance_col="_dist_m")
        nearest = nearest[~nearest.index.duplicated(keep="first")]
        return (nearest["_dist_m"] / 1000).round(3)

    df["forest_distance_km"] = _nearest_km(zones_m[zones_m["_kind"] == "forest"]).values
    df["water_distance_km"] = _nearest_km(zones_m[zones_m["_kind"] == "water"]).values

    agri = zones_m[zones_m["_kind"] == "agricultural"]
    if not agri.empty:
        agri_buffered = agri.copy()
        agri_buffered["geometry"] = agri_buffered.geometry.buffer(config.INDUSTRIAL_BUFFER_M)
        agri_wgs = agri_buffered.dissolve()[["geometry"]].to_crs("EPSG:4326")
        points_wgs = _points_gdf(df)
        hit = gpd.sjoin(points_wgs, agri_wgs, how="left", predicate="within")["index_right"].notna().values
        df["in_agricultural_zone"] = hit

    return df
