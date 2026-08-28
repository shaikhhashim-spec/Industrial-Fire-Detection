"""Spatial cluster analysis: group nearby ~1km grid-cell events into
broader multi-cell "fire clusters" (e.g. several adjacent cells that are
really one large industrial complex) using DBSCAN over haversine distance.
A complement to the persistence engine's own 1km grid, not a replacement —
the grid decides what one *event* is; this decides which events sit close
enough together to plausibly be one larger *site*.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN

EARTH_RADIUS_KM = 6371.0
DEFAULT_EPS_KM = 2.0       # events within this distance are grouped together
DEFAULT_MIN_SAMPLES = 2    # a "cluster" needs at least this many events


def find_spatial_clusters(
    cluster_df: pd.DataFrame, eps_km: float = DEFAULT_EPS_KM, min_samples: int = DEFAULT_MIN_SAMPLES
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (cluster_df + `spatial_cluster_id` column [-1 = not part of
    any multi-event cluster], summary_df — one row per spatial cluster)."""
    out = cluster_df.copy()
    if out.empty or len(out) < min_samples:
        out["spatial_cluster_id"] = -1
        return out, pd.DataFrame()

    coords = np.radians(out[["latitude", "longitude"]].to_numpy())
    labels = DBSCAN(eps=eps_km / EARTH_RADIUS_KM, min_samples=min_samples, metric="haversine").fit_predict(coords)
    out["spatial_cluster_id"] = labels

    clustered = out[out["spatial_cluster_id"] >= 0]
    if clustered.empty:
        return out, pd.DataFrame()

    summary = (
        clustered.groupby("spatial_cluster_id")
        .agg(
            n_events=("grid_cell", "size"),
            total_detections=("detection_count", "sum") if "detection_count" in clustered.columns else ("grid_cell", "size"),
            avg_risk=("risk_score", "mean") if "risk_score" in clustered.columns else ("grid_cell", "size"),
            max_risk=("risk_score", "max") if "risk_score" in clustered.columns else ("grid_cell", "size"),
            latitude=("latitude", "mean"),
            longitude=("longitude", "mean"),
        )
        .reset_index()
        .sort_values("max_risk", ascending=False)
    )
    summary["avg_risk"] = summary["avg_risk"].round(1)
    return out, summary
