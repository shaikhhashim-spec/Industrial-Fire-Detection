"""Feature engineering: merge each detection with its grid cell's aggregate
activity profile and derive the numeric/boolean features the rule engine,
risk scorer, and ML classifier all consume.

Scope note: forest-proximity, water-proximity, and a real OSM-polygon-backed
agricultural-zone boolean are NOT implemented here. Fetching those layers
(natural=wood, natural=water, landuse=farmland) over the full bounding box
would make the already-flaky public Overpass endpoint (see
src/geospatial/osm.py — it has already timed out during development) far
more likely to fail, for features the rule engine can approximate from
existing signals (industrial-zone absence + burn-season month). This is a
deliberate reliability tradeoff, not an oversight — see README.md "Future
Improvements".
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import config

CLUSTER_COLUMNS = (
    ["detection_count", "avg_frp", "max_frp", "first_detected", "last_detected", "recurrence_frequency"]
    + [f"persistence_{w}d" for w in config.PERSISTENCE_WINDOWS_DAYS]
    + [f"detections_{w}d" for w in config.PERSISTENCE_WINDOWS_DAYS]
)

# Features fed to the ML classifier — numeric/boolean only, normalized where
# scale varies wildly (FRP, distance) so no single feature dominates purely
# from having a bigger numeric range.
ML_FEATURE_COLUMNS = [
    "frp", "brightness", "confidence_numeric", "persistence_days", "detection_count",
    "avg_frp", "max_frp", "frp_trend", "industrial_distance_km", "mine_distance_km",
    "industrial_zone_flag", "recurrence_frequency", "detections_7d", "daynight_flag",
    "forest_distance_km", "water_distance_km", "agricultural_zone_flag",
]


def build_features(df: pd.DataFrame, cluster_summary: pd.DataFrame) -> pd.DataFrame:
    """Row-level detections in, the same rows out with cluster-aggregate and
    derived features attached."""
    df = df.copy()
    if cluster_summary is not None and not cluster_summary.empty:
        cols = ["grid_cell"] + [c for c in CLUSTER_COLUMNS if c in cluster_summary.columns]
        df = df.merge(cluster_summary[cols], on="grid_cell", how="left")

    for col in CLUSTER_COLUMNS:
        if col not in df.columns:
            df[col] = 0

    df["frp_trend"] = np.where(df["avg_frp"] > 0, (df["frp"] / df["avg_frp"]).round(3), 1.0)
    df["industrial_zone_flag"] = (df.get("zone_type") == "industrial").astype(int)
    df["mine_zone_flag"] = (df.get("mine_distance_km", pd.Series(dtype=float)).fillna(999) < 0.05).astype(int)
    df["daynight_flag"] = (df.get("daynight") == "D").astype(int)
    df["agricultural_zone_flag"] = df.get("in_agricultural_zone", False).fillna(False).astype(int) \
        if "in_agricultural_zone" in df.columns else 0
    if "forest_distance_km" not in df.columns:
        df["forest_distance_km"] = float("nan")
    if "water_distance_km" not in df.columns:
        df["water_distance_km"] = float("nan")

    if "brightness" not in df.columns:
        df["brightness"] = df.get("bright_ti4", df.get("bright_t31", 0.0))

    return df


def normalized_ml_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Min-max normalize the ML feature columns to [0,1] for the classifier,
    leaving the source dataframe untouched."""
    X = df[[c for c in ML_FEATURE_COLUMNS if c in df.columns]].fillna(0).astype(float)
    ranges = X.max() - X.min()
    ranges = ranges.replace(0, 1)
    return (X - X.min()) / ranges
