"""Snap hotspots to a coarse grid and count how many distinct days each cell
has fired, to separate persistent thermal sources from one-off detections.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import config


def assign_grid_cell(df: pd.DataFrame, grid_size: float = config.GRID_SIZE_DEG) -> pd.DataFrame:
    df = df.copy()
    df["grid_lat"] = (np.floor(df["latitude"] / grid_size) * grid_size).round(5)
    df["grid_lon"] = (np.floor(df["longitude"] / grid_size) * grid_size).round(5)
    df["grid_cell"] = df["grid_lat"].astype(str) + "_" + df["grid_lon"].astype(str)
    return df


def compute_persistence(
    df: pd.DataFrame,
    grid_size: float = config.GRID_SIZE_DEG,
    min_days: int = config.PERSISTENCE_MIN_DAYS,
) -> pd.DataFrame:
    """Add `grid_cell`, `persistence_days` (distinct acq_date count per cell
    across the whole fetched window) and `is_persistent` columns."""
    df = assign_grid_cell(df, grid_size)
    day_counts = df.groupby("grid_cell")["acq_date"].nunique().rename("persistence_days")
    df = df.merge(day_counts, on="grid_cell", how="left")
    df["is_persistent"] = df["persistence_days"] >= min_days
    return df
