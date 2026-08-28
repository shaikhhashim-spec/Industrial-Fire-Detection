"""Snap hotspots to a coarse (~1km) grid so repeated detections at
essentially the same spot can be grouped and counted."""
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


def grid_cell_center(grid_cell: str, grid_size: float = config.GRID_SIZE_DEG) -> tuple[float, float]:
    """Lat/lon of a grid cell's center, given its 'lat_lon' cell id."""
    glat, glon = (float(x) for x in grid_cell.split("_"))
    return glat + grid_size / 2, glon + grid_size / 2
