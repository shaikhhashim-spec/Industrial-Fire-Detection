"""Hotspot lifecycle status: NEW / RECURRING / PERSISTENT / HIGH RISK /
CRITICAL / RESOLVED-INACTIVE.

"now" is taken as the most recent acq_date present in the batch being
scored, not the wall-clock date, so status assignment stays stable on a
frozen demo dataset no matter when the demo is actually run, matching the
platform's own Demo Mode guarantee (never depend on external freshness).
"""
from __future__ import annotations

import pandas as pd

import config

STATUS_NEW = "NEW"
STATUS_RECURRING = "RECURRING"
STATUS_PERSISTENT = "PERSISTENT"
STATUS_HIGH_RISK = "HIGH RISK"
STATUS_CRITICAL = "CRITICAL"
STATUS_INACTIVE = "RESOLVED/INACTIVE"


def _status_for_row(row, now: pd.Timestamp) -> str:
    risk = row.get("risk_score", 0)
    persistent = bool(row.get("is_persistent", False))
    days_since_last = (now - row["last_detected"]).days if pd.notna(row.get("last_detected")) else 0
    days_since_first = (now - row["first_detected"]).days if pd.notna(row.get("first_detected")) else 0
    detections = row.get("detection_count", 1)

    # Priority: CRITICAL > HIGH RISK > INACTIVE > PERSISTENT > RECURRING > NEW
    if risk >= config.ALERT_CRITICAL_RISK_MIN:
        return STATUS_CRITICAL
    if risk >= config.ALERT_HIGH_RISK_MIN:
        return STATUS_HIGH_RISK
    if days_since_last > config.STATUS_INACTIVE_AFTER_DAYS:
        return STATUS_INACTIVE
    if persistent:
        return STATUS_PERSISTENT
    if detections > 1:
        return STATUS_RECURRING
    if days_since_first <= config.STATUS_NEW_WITHIN_DAYS:
        return STATUS_NEW
    return STATUS_RECURRING


def assign_status(cluster_df: pd.DataFrame) -> pd.DataFrame:
    """Add a `status` column to a per-cluster (grid-cell-level) dataframe that
    already has `first_detected`, `last_detected`, `detection_count`,
    `is_persistent`, and `risk_score`."""
    cluster_df = cluster_df.copy()
    if cluster_df.empty:
        cluster_df["status"] = pd.Series(dtype="object")
        return cluster_df
    now = cluster_df["last_detected"].max()
    cluster_df["status"] = cluster_df.apply(lambda r: _status_for_row(r, now), axis=1)
    return cluster_df
