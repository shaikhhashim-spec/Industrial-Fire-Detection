"""Human-readable, stable event identifiers for grid-cell events.

Deterministic from the grid cell's own id (not a sequential counter) so the
same real-world location gets the same event_id run over run, filter over
filter — it never shifts just because the dataset around it changed. It is
a display label, not a registration number: nothing about "TH-4F2A91"
claims official/sequential provenance.
"""
from __future__ import annotations

import hashlib

import pandas as pd


def event_id_for_cell(grid_cell: str) -> str:
    digest = hashlib.md5(str(grid_cell).encode()).hexdigest()[:6].upper()
    return f"TH-{digest}"


def add_event_ids(df: pd.DataFrame, cell_col: str = "grid_cell") -> pd.DataFrame:
    df = df.copy()
    df["event_id"] = df[cell_col].astype(str).map(event_id_for_cell)
    return df
