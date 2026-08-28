"""Prototype Operational Risk Score (0-100) — NOT an official government
fire-risk standard. A weighted blend of five component scores, each
independently normalized to 0-100 before weighting, so the weights in
config.RISK_WEIGHTS mean what they say."""
from __future__ import annotations

import pandas as pd

import config


def _persistence_score(row) -> float:
    window = config.PERSISTENCE_DEFAULT_WINDOW_DAYS
    return min(100.0, (row.get("persistence_days", 0) / window) * 100)


def _frp_score(row) -> float:
    return min(100.0, (row.get("frp", 0) / config.FRP_HIGH_MIN) * 100)


def _confidence_score(row) -> float:
    return max(0.0, min(100.0, float(row.get("confidence_numeric", 0))))


def _proximity_score(row) -> float:
    if row.get("zone_type") == "industrial":
        return 100.0
    dist = row.get("industrial_distance_km")
    if pd.isna(dist):
        return 0.0
    return max(0.0, 100.0 - (min(dist, 5.0) / 5.0) * 100)


def _recurrence_score(row) -> float:
    return min(100.0, float(row.get("recurrence_frequency", 0)) * 100)


COMPONENTS = {
    "persistence": _persistence_score,
    "frp": _frp_score,
    "confidence": _confidence_score,
    "industrial_proximity": _proximity_score,
    "recurrence": _recurrence_score,
}


def risk_level(score: float) -> str:
    for low, high, label in config.RISK_LEVELS:
        if low <= score <= high:
            return label
    return "LOW"


def _score_row(row, weights: dict) -> tuple[float, dict]:
    breakdown = {name: fn(row) for name, fn in COMPONENTS.items()}
    total = sum(breakdown[name] * weights.get(name, 0) for name in breakdown)
    total = max(0.0, min(100.0, total))  # defensive: weights are user-configurable and may not sum to exactly 1.0
    return round(total, 1), breakdown


def compute_risk(df: pd.DataFrame, weights: dict | None = None) -> pd.DataFrame:
    """Add `risk_score` (0-100), `risk_level`, and per-component
    `risk_component_<name>` columns (for the investigation panel's
    contributing-factors view)."""
    weights = weights or config.RISK_WEIGHTS
    df = df.copy()
    if df.empty:
        df["risk_score"] = pd.Series(dtype=float)
        df["risk_level"] = pd.Series(dtype=str)
        return df

    scores, breakdowns = [], []
    for _, row in df.iterrows():
        s, b = _score_row(row, weights)
        scores.append(s)
        breakdowns.append(b)

    df["risk_score"] = scores
    df["risk_level"] = df["risk_score"].apply(risk_level)
    for name in COMPONENTS:
        df[f"risk_component_{name}"] = [b[name] for b in breakdowns]
    return df
