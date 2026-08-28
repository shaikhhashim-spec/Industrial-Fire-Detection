"""Persistent SQLite accumulation of national (India-wide) FIRMS
observations — deliberately minimal (raw + state-tagged input columns
only, no OSM/AI columns): the national layer's own staged-architecture
scope stays detection + persistence, never classification (see
src/national/pipeline.py's module docstring). Every live run's fresh
pull is merged in here so persistence is judged against real accumulated
history instead of only ever the latest 24-48h snapshot. Never touched in
Demo Mode — same demo/live isolation guarantee as the regional store
(src/store.py), so synthetic demo rows can never contaminate real history.
"""
from __future__ import annotations

import sqlite3

import pandas as pd

import config

DB_PATH = config.NATIONAL_DB_PATH

INPUT_COLUMNS = [
    "latitude", "longitude", "acq_date", "acq_time", "satellite", "instrument",
    "confidence", "confidence_numeric", "frp", "daynight", "source", "state",
]
NATURAL_KEY = ["latitude", "longitude", "acq_date", "acq_time", "satellite", "source"]
_TEXT_COLUMNS = {"acq_date", "satellite", "instrument", "confidence", "daynight", "source", "state"}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    col_defs = ", ".join(f"{c} TEXT" if c in _TEXT_COLUMNS else f"{c} REAL" for c in INPUT_COLUMNS)
    conn.execute(f"CREATE TABLE IF NOT EXISTS national_hotspots ({col_defs}, PRIMARY KEY ({','.join(NATURAL_KEY)}))")
    return conn


def upsert(df: pd.DataFrame) -> None:
    """Insert new observations / overwrite matching ones (same natural key)."""
    if df.empty:
        return
    cols = [c for c in INPUT_COLUMNS if c in df.columns]
    work = df[cols].copy()
    work["acq_date"] = work["acq_date"].astype(str)
    rows = work.astype(object).where(pd.notnull(work), None).values.tolist()
    placeholders = ",".join("?" * len(cols))
    with _connect() as conn:
        conn.executemany(f"INSERT OR REPLACE INTO national_hotspots ({','.join(cols)}) VALUES ({placeholders})", rows)


def load_history(days: int | None = None) -> pd.DataFrame:
    """Every accumulated observation, optionally restricted to the last
    `days` (relative to the store's own most recent date, so it stays
    stable regardless of wall-clock time between runs)."""
    if not DB_PATH.exists():
        return pd.DataFrame(columns=INPUT_COLUMNS)
    with _connect() as conn:
        df = pd.read_sql(f"SELECT {','.join(INPUT_COLUMNS)} FROM national_hotspots", conn)
    if df.empty:
        return df
    df["acq_date"] = pd.to_datetime(df["acq_date"])
    if days:
        cutoff = df["acq_date"].max() - pd.Timedelta(days=days)
        df = df[df["acq_date"] > cutoff].reset_index(drop=True)
    return df


def count() -> int:
    if not DB_PATH.exists():
        return 0
    with _connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM national_hotspots").fetchone()[0]


def days_covered() -> int:
    """Distinct calendar days of history currently stored — shown in the UI
    so it's clear how much real accumulated history persistence is being
    judged against right now."""
    if not DB_PATH.exists():
        return 0
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(DISTINCT acq_date) FROM national_hotspots").fetchone()
    return row[0] if row else 0
