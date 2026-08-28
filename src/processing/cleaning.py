"""Data cleaning: raw FIRMS rows in, validated rows out. Keeps a small report
of what was dropped and why, so data quality is visible rather than silent."""
from __future__ import annotations

import pandas as pd

import config

REQUIRED_COLUMNS = ["latitude", "longitude", "acq_date", "acq_time", "frp", "confidence", "satellite"]
VALID_SATELLITES = {"N", "N20", "N21", "Terra", "Aqua", "1", "T", "A"}  # FIRMS satellite codes seen across sources


def clean_hotspots(df: pd.DataFrame, bbox: dict | None = None) -> tuple[pd.DataFrame, dict]:
    """Return (clean_df, report). report counts rows dropped at each stage so
    data quality is auditable instead of a silent shrink.

    bbox defaults to the detailed Jharkhand-Odisha region; national-mode
    callers pass a country-wide bbox (or None to skip the region filter
    entirely, since the FIRMS country endpoint already scopes to India)."""
    report = {"input_rows": len(df)}
    if df.empty:
        report["output_rows"] = 0
        return df, report

    df = df.copy()

    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        report["missing_columns"] = missing_cols
        for c in missing_cols:
            df[c] = None

    before = len(df)
    df = df.dropna(subset=["latitude", "longitude", "acq_date"])
    report["dropped_missing_coords_or_date"] = before - len(df)

    before = len(df)
    df["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    df = df.dropna(subset=["latitude", "longitude"])
    df = df[df["latitude"].between(-90, 90) & df["longitude"].between(-180, 180)]
    report["dropped_invalid_coords"] = before - len(df)

    if bbox is None:
        bbox = config.BBOX
    if bbox:
        before = len(df)
        df = df[
            df["latitude"].between(bbox["min_lat"], bbox["max_lat"])
            & df["longitude"].between(bbox["min_lon"], bbox["max_lon"])
        ]
        report["dropped_outside_bbox"] = before - len(df)
    else:
        report["dropped_outside_bbox"] = 0

    before = len(df)
    df["frp"] = pd.to_numeric(df["frp"], errors="coerce").fillna(0.0).clip(lower=0)
    report["frp_coerced_or_clipped"] = before  # informational, not a drop

    df["confidence"] = df["confidence"].apply(lambda v: v if pd.notna(v) else 50)

    df["acq_date"] = pd.to_datetime(df["acq_date"], errors="coerce")
    before = len(df)
    df = df.dropna(subset=["acq_date"])
    report["dropped_bad_dates"] = before - len(df)

    df["acq_time"] = pd.to_numeric(df["acq_time"], errors="coerce").fillna(0).astype(int)

    df["satellite"] = df["satellite"].astype(str).str.strip()
    df.loc[~df["satellite"].isin(VALID_SATELLITES), "satellite"] = df["satellite"]  # keep unknown but flagged, don't drop
    report["unrecognized_satellite_codes"] = int((~df["satellite"].isin(VALID_SATELLITES)).sum())

    dedupe_keys = [c for c in ["latitude", "longitude", "acq_date", "acq_time", "satellite"] if c in df.columns]
    before = len(df)
    df = df.drop_duplicates(subset=dedupe_keys)
    report["dropped_duplicates"] = before - len(df)

    report["output_rows"] = len(df)
    return df.reset_index(drop=True), report
