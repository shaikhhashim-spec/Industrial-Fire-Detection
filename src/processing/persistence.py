"""Persistence engine: how many distinct days has each ~1km grid cell been
thermally active, across 7/30/60-day windows, and what does that cell's
detection history look like overall.
"""
from __future__ import annotations

import pandas as pd

import config
from src.geospatial.grid import assign_grid_cell


def compute_persistence(
    df: pd.DataFrame,
    grid_size: float = config.GRID_SIZE_DEG,
    min_days: int = config.PERSISTENCE_MIN_DAYS,
) -> pd.DataFrame:
    """Row-level: add `grid_cell`, `persistence_days` (distinct-day count for
    that cell across the whole input batch) and `is_persistent`."""
    df = assign_grid_cell(df, grid_size)
    day_counts = df.groupby("grid_cell")["acq_date"].nunique().rename("persistence_days")
    df = df.merge(day_counts, on="grid_cell", how="left")
    df["is_persistent"] = df["persistence_days"] >= min_days
    return df


def build_cluster_summary(df: pd.DataFrame, min_days: int = config.PERSISTENCE_MIN_DAYS) -> pd.DataFrame:
    """One row per grid cell with the full activity profile: detection
    count, FRP/confidence stats, first/last seen, and persistence counted
    over each of the 7/30/60-day windows (relative to the batch's own most
    recent date, so it works the same on live or frozen demo data).
    """
    if df.empty:
        return pd.DataFrame()

    df = assign_grid_cell(df) if "grid_cell" not in df.columns else df
    now = df["acq_date"].max()

    agg_spec = dict(
        detection_count=("acq_date", "size"),
        avg_frp=("frp", "mean"),
        max_frp=("frp", "max"),
        avg_confidence=("confidence_numeric", "mean") if "confidence_numeric" in df.columns else ("frp", "size"),
        first_detected=("acq_date", "min"),
        last_detected=("acq_date", "max"),
        latitude=("latitude", "mean"),
        longitude=("longitude", "mean"),
    )
    if "satellite" in df.columns:
        agg_spec["satellites"] = ("satellite", lambda s: sorted(set(s.dropna().astype(str))))

    base = df.groupby("grid_cell").agg(**agg_spec).reset_index()

    for window in config.PERSISTENCE_WINDOWS_DAYS:
        cutoff = now - pd.Timedelta(days=window)
        windowed = df[df["acq_date"] > cutoff]
        day_counts = windowed.groupby("grid_cell")["acq_date"].nunique().rename(f"persistence_{window}d")
        det_counts = windowed.groupby("grid_cell").size().rename(f"detections_{window}d")
        base = base.merge(day_counts, on="grid_cell", how="left").merge(det_counts, on="grid_cell", how="left")
        base[f"persistence_{window}d"] = base[f"persistence_{window}d"].fillna(0).astype(int)
        base[f"detections_{window}d"] = base[f"detections_{window}d"].fillna(0).astype(int)

    default_col = f"persistence_{config.PERSISTENCE_DEFAULT_WINDOW_DAYS}d"
    base["is_persistent"] = base[default_col] >= min_days

    span_days = (base["last_detected"] - base["first_detected"]).dt.days.clip(lower=0) + 1
    base["recurrence_frequency"] = (base["detection_count"] / span_days).round(3)

    return base.sort_values(default_col, ascending=False).reset_index(drop=True)
