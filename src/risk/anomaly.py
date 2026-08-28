"""Per-cell thermal anomaly detection — simple, explainable baseline
statistics (rolling mean + standard deviation -> z-score), deliberately
kept simple rather than reaching for something like Isolation Forest, per
the platform's own guidance to prefer simple methods first here.

For each grid cell, the most recent detection is compared against a
baseline built from that same cell's OWN earlier detections (never a
cross-cell/global baseline, since normal FRP varies hugely between e.g. a
small facility and a large steel plant). A cell needs at least
ANOMALY_MIN_BASELINE_POINTS prior detections before an anomaly verdict is
attempted at all — with too little history there's no honest baseline to
deviate from, so it is reported as "insufficient history", not "normal".

This is a distinct, additive signal from the existing ratio-based
`frp_spike` alert in src/alerts/engine.py (max vs avg across the whole
window) — that check stays as-is so its existing tests/behavior are
untouched. This module answers a different, complementary question: does
the single most recent detection look statistically unusual for this
specific location's own history."""
from __future__ import annotations

import pandas as pd

import config

ANOMALY_MIN_BASELINE_POINTS = 2   # need at least this many prior detections to form a baseline
ANOMALY_ZSCORE_MIN = 2.0          # >= this many std deviations above baseline
ANOMALY_RATIO_MIN = config.ALERT_FRP_SPIKE_MULTIPLIER  # backstop for near-zero-variance baselines


def compute_frp_anomaly(detail_df: pd.DataFrame) -> pd.DataFrame:
    """Return one row per grid_cell with: frp_baseline_mean,
    frp_baseline_std, latest_frp, frp_zscore, frp_change_pct,
    has_baseline, is_anomalous."""
    empty_result = pd.DataFrame(columns=["grid_cell", "frp_baseline_mean", "frp_baseline_std", "latest_frp",
                                          "frp_zscore", "frp_change_pct", "has_baseline", "is_anomalous"])
    if detail_df is None or detail_df.empty or not {"grid_cell", "acq_date", "frp"} <= set(detail_df.columns):
        return empty_result

    rows = []
    for cell, group in detail_df.groupby("grid_cell"):
        ordered = group.sort_values("acq_date")
        latest_frp = float(ordered["frp"].iloc[-1])
        baseline = ordered["frp"].iloc[:-1]

        if len(baseline) < ANOMALY_MIN_BASELINE_POINTS:
            rows.append({
                "grid_cell": cell, "frp_baseline_mean": float("nan"), "frp_baseline_std": float("nan"),
                "latest_frp": latest_frp, "frp_zscore": float("nan"), "frp_change_pct": float("nan"),
                "has_baseline": False, "is_anomalous": False,
            })
            continue

        mean, std = float(baseline.mean()), float(baseline.std(ddof=0))
        change_pct = ((latest_frp - mean) / mean * 100) if mean > 0 else 0.0
        zscore = ((latest_frp - mean) / std) if std > 1e-6 else float("inf") if latest_frp > mean else 0.0
        ratio = (latest_frp / mean) if mean > 0 else 1.0

        is_anomalous = zscore >= ANOMALY_ZSCORE_MIN and ratio >= ANOMALY_RATIO_MIN
        rows.append({
            "grid_cell": cell, "frp_baseline_mean": round(mean, 2), "frp_baseline_std": round(std, 2),
            "latest_frp": round(latest_frp, 2),
            "frp_zscore": round(zscore, 2) if zscore != float("inf") else zscore,
            "frp_change_pct": round(change_pct, 1), "has_baseline": True, "is_anomalous": bool(is_anomalous),
        })

    return pd.DataFrame(rows)
