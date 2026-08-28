"""SQLite persistent store — the "database" component of the platform.

Every classify_hotspots() call upserts its rows here (keyed by each
detection's natural FIRMS identity), so records accumulate across repeated
runs instead of being lost when output/ is overwritten. On the next call,
input history is pulled back out and merged with the freshly handed-off
batch before persistence/risk/classification are recomputed — so a
detection FIRMS's live feed no longer serves still counts.
"""
from __future__ import annotations

import sqlite3

import pandas as pd

import config

DB_PATH = config.DB_PATH

# Columns handed to classify_hotspots() from upstream (fetch + geospatial
# join) — preserved as-is across runs, never recomputed by this module.
INPUT_COLUMNS = [
    "latitude", "longitude", "brightness", "scan", "track", "acq_date", "acq_time",
    "satellite", "instrument", "confidence", "version", "bright_t31", "frp", "daynight",
    "source", "zone_type", "zone_kind", "industrial_distance_km", "mine_distance_km", "power_distance_km",
    "nearest_industrial_name", "forest_distance_km", "water_distance_km", "in_agricultural_zone",
]
# Columns classify_hotspots() computes itself.
COMPUTED_COLUMNS = [
    "grid_lat", "grid_lon", "grid_cell", "persistence_days", "is_persistent",
    "confidence_numeric", "rule_label", "rule_reason", "rule_evidence",
    "ml_label", "ml_confidence", "risk_score", "risk_level",
    "risk_component_persistence", "risk_component_frp", "risk_component_confidence",
    "risk_component_industrial_proximity", "risk_component_recurrence",
]
ALL_COLUMNS = INPUT_COLUMNS + COMPUTED_COLUMNS
NATURAL_KEY = ["latitude", "longitude", "acq_date", "acq_time", "satellite", "source"]

_TEXT_COLUMNS = {"acq_date", "satellite", "instrument", "confidence",
    "version", "daynight", "source", "zone_type", "zone_kind", "nearest_industrial_name", "grid_cell", "rule_label",
    "rule_reason", "rule_evidence", "ml_label", "risk_level"}
_COLUMN_DEFS = ", ".join(f"{c} TEXT" if c in _TEXT_COLUMNS else f"{c} REAL" for c in ALL_COLUMNS)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(f"CREATE TABLE IF NOT EXISTS hotspots ({_COLUMN_DEFS}, PRIMARY KEY ({','.join(NATURAL_KEY)}))")
    _ensure_columns(conn)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS analyst_reviews ("
        "event_id TEXT PRIMARY KEY, grid_cell TEXT, region TEXT, decision TEXT, notes TEXT, reviewed_at TEXT)"
    )
    return conn


def _ensure_columns(conn: sqlite3.Connection) -> None:
    """Schema evolves as new fields are added (e.g. zone_kind, power_distance_km
    in a later iteration) — ALTER TABLE ADD COLUMN for anything ALL_COLUMNS
    now expects that an existing on-disk DB predates, rather than requiring
    a manual DB reset every time a column is added."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(hotspots)")}
    for col in ALL_COLUMNS:
        if col not in existing:
            col_type = "TEXT" if col in _TEXT_COLUMNS else "REAL"
            conn.execute(f"ALTER TABLE hotspots ADD COLUMN {col} {col_type}")


def upsert(df: pd.DataFrame) -> None:
    """Insert new rows / overwrite matching ones (same natural key)."""
    if df.empty:
        return
    cols = [c for c in ALL_COLUMNS if c in df.columns]
    work = df[cols].copy()
    work["acq_date"] = work["acq_date"].astype(str)
    if "is_persistent" in work:
        work["is_persistent"] = work["is_persistent"].astype(int)
    if "in_agricultural_zone" in work:
        work["in_agricultural_zone"] = work["in_agricultural_zone"].astype(int)
    rows = work.astype(object).where(pd.notnull(work), None).values.tolist()
    placeholders = ",".join("?" * len(cols))
    with _connect() as conn:
        conn.executemany(f"INSERT OR REPLACE INTO hotspots ({','.join(cols)}) VALUES ({placeholders})", rows)


def load_input_history() -> pd.DataFrame:
    """Input fields (pre-classification, but geospatially-tagged) for every
    record ever stored — extends the persistence window beyond a single
    handed-off batch."""
    if not DB_PATH.exists():
        return pd.DataFrame()
    with _connect() as conn:
        df = pd.read_sql(f"SELECT {','.join(INPUT_COLUMNS)} FROM hotspots", conn)
    if not df.empty:
        df["acq_date"] = pd.to_datetime(df["acq_date"])
    return df


def load_all() -> pd.DataFrame:
    """Every column, every record — the full historical classified set."""
    if not DB_PATH.exists():
        return pd.DataFrame()
    with _connect() as conn:
        df = pd.read_sql("SELECT * FROM hotspots", conn)
    if not df.empty:
        df["acq_date"] = pd.to_datetime(df["acq_date"])
        if "is_persistent" in df.columns:
            df["is_persistent"] = df["is_persistent"].astype(bool)
    return df


def count() -> int:
    if not DB_PATH.exists():
        return 0
    with _connect() as conn:
        return conn.execute("SELECT COUNT(*) FROM hotspots").fetchone()[0]


# --- Analyst review audit trail ---------------------------------------------
# Persists human-in-the-loop decisions (Confirm/Reject/Needs Verification)
# from the Validation page, keyed by event_id, so they survive a page
# refresh or a new pipeline run — the platform's own audit-trail
# requirement, kept intentionally simple: one row per event holding its
# latest decision, not a full multi-review history log.

def save_review(event_id: str, grid_cell: str, region: str, decision: str, notes: str = "") -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO analyst_reviews (event_id, grid_cell, region, decision, notes, reviewed_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (event_id, grid_cell, region, decision, notes, pd.Timestamp.now().isoformat()),
        )


def load_reviews(region: str | None = None) -> pd.DataFrame:
    if not DB_PATH.exists():
        return pd.DataFrame(columns=["event_id", "grid_cell", "region", "decision", "notes", "reviewed_at"])
    with _connect() as conn:
        if region:
            df = pd.read_sql("SELECT * FROM analyst_reviews WHERE region = ?", conn, params=(region,))
        else:
            df = pd.read_sql("SELECT * FROM analyst_reviews", conn)
    return df
