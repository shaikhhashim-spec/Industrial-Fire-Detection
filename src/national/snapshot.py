"""The latest successful *live* national run, persisted so every consumer shows
the same data without recomputing it: the Streamlit dashboard adopts it on
startup (instead of "No national data yet"), and the 3D globe's events.json is
exported from the very same run.

Written only for real FIRMS data — a demo run never replaces it.
"""
from __future__ import annotations

import pandas as pd

import config

SNAPSHOT_PATH = config.PROCESSED_DIR / "national_latest.pkl"


def save(info: dict) -> None:
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = SNAPSHOT_PATH.with_suffix(".tmp")
    pd.to_pickle(info, tmp)
    tmp.replace(SNAPSHOT_PATH)  # atomic: a reader never sees a half-written file


def mtime() -> float | None:
    return SNAPSHOT_PATH.stat().st_mtime if SNAPSHOT_PATH.exists() else None


def load() -> dict | None:
    """The saved run, or None if there isn't one (or it can't be read)."""
    if not SNAPSHOT_PATH.exists():
        return None
    try:
        info = pd.read_pickle(SNAPSHOT_PATH)
    except Exception as exc:  # stale format after an upgrade, partial copy, …
        print(f"[national.snapshot] ignoring unreadable snapshot: {exc}")
        return None
    return info if isinstance(info, dict) and "events_df" in info else None
