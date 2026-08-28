"""Alert generation from the classified, cluster-level dataset. Alerts are
recomputed fresh from the current data on every run — not a stateful diff
against a previous run's alert log (there's no "alert history" store yet;
see README "Future Improvements")."""
from __future__ import annotations

import pandas as pd

import config
from src.risk.anomaly import compute_frp_anomaly

ALERT_TITLES = {
    "critical_risk": "CRITICAL THERMAL EVENT",
    "high_risk_persistent": "PERSISTENT HIGH-RISK SOURCE",
    "frp_spike": "SUDDEN FRP INCREASE",
    "reactivated": "REACTIVATED THERMAL SOURCE",
    "thermal_anomaly": "THERMAL ANOMALY DETECTED",
}
SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MODERATE": 2}


def _reactivation_flags(detail_df: pd.DataFrame) -> dict:
    """Per grid cell: True if there's a gap longer than
    STATUS_INACTIVE_AFTER_DAYS between two consecutive detections and the
    most recent detection is within a day of the batch's own 'now'."""
    if detail_df.empty:
        return {}
    now = detail_df["acq_date"].max()
    flags = {}
    for cell, group in detail_df.groupby("grid_cell"):
        dates = sorted(group["acq_date"].unique())
        if len(dates) < 2:
            flags[cell] = False
            continue
        recent = (now - pd.Timestamp(dates[-1])).days <= 1
        gap = any(
            (pd.Timestamp(b) - pd.Timestamp(a)).days > config.STATUS_INACTIVE_AFTER_DAYS
            for a, b in zip(dates, dates[1:])
        )
        flags[cell] = bool(recent and gap)
    return flags


def generate_alerts(detail_df: pd.DataFrame, cluster_df: pd.DataFrame) -> list[dict]:
    """Return alert dicts, most severe first. `detail_df` is row-level
    classified data; `cluster_df` is one row per grid cell with
    risk_score/status/detection stats already attached."""
    if cluster_df is None or cluster_df.empty:
        return []

    reactivated = _reactivation_flags(detail_df)
    anomaly = compute_frp_anomaly(detail_df).set_index("grid_cell") if detail_df is not None and not detail_df.empty else pd.DataFrame()
    default_window = config.PERSISTENCE_DEFAULT_WINDOW_DAYS
    alerts = []

    for _, row in cluster_df.iterrows():
        cell = row["grid_cell"]
        base = {
            "grid_cell": cell,
            "event_id": row.get("event_id", cell),
            "latitude": row.get("latitude"),
            "longitude": row.get("longitude"),
            "classification": row.get("dominant_label", "Requires Verification"),
            "risk_score": row.get("risk_score", 0),
            "risk_level": row.get("risk_level", "LOW"),
            "persistence_days": row.get(f"persistence_{default_window}d", 0),
            "frp": row.get("avg_frp", 0),
            "industrial_distance_km": row.get("industrial_distance_km"),
            "status": row.get("status", ""),
        }

        risk = row.get("risk_score", 0)
        if risk >= config.ALERT_CRITICAL_RISK_MIN:
            alerts.append({**base, "type": "critical_risk", "title": ALERT_TITLES["critical_risk"], "severity": "CRITICAL"})
        elif risk >= config.ALERT_HIGH_RISK_MIN and row.get("is_persistent"):
            alerts.append({**base, "type": "high_risk_persistent", "title": ALERT_TITLES["high_risk_persistent"], "severity": "HIGH"})

        max_frp, avg_frp = row.get("max_frp", 0), row.get("avg_frp", 0)
        if avg_frp > 0 and max_frp >= avg_frp * config.ALERT_FRP_SPIKE_MULTIPLIER and max_frp >= config.FRP_INDUSTRIAL_MIN:
            alerts.append({**base, "type": "frp_spike", "title": ALERT_TITLES["frp_spike"], "severity": "MODERATE"})

        if reactivated.get(cell, False):
            alerts.append({**base, "type": "reactivated", "title": ALERT_TITLES["reactivated"], "severity": "MODERATE"})

        if not anomaly.empty and cell in anomaly.index and bool(anomaly.loc[cell, "is_anomalous"]):
            alerts.append({**base, "type": "thermal_anomaly", "title": ALERT_TITLES["thermal_anomaly"], "severity": "HIGH"})

    alerts.sort(key=lambda a: (SEVERITY_ORDER.get(a["severity"], 9), -a["risk_score"]))
    return alerts
