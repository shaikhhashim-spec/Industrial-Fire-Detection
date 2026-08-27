"""Rule-based classification (v1) combining confidence, FRP, persistence and
zone context into a human-readable label. This is the explainable baseline
the ML layer (src/ml_model.py) is trained against and validated with."""
from __future__ import annotations

import pandas as pd

import config

# VIIRS reports confidence as l/n/h; MODIS reports 0-100. Normalize both to
# a single 0-100 scale so downstream thresholds are consistent.
_VIIRS_CONF_MAP = {"l": 30, "n": 60, "h": 90}


def normalize_confidence(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    def _norm(val):
        if isinstance(val, str):
            return _VIIRS_CONF_MAP.get(val.strip().lower(), 50)
        try:
            return float(val)
        except (TypeError, ValueError):
            return 50.0

    df["confidence_numeric"] = df["confidence"].apply(_norm)
    return df


def _classify_row(row) -> tuple[str, str]:
    """Return (label, reason) — reason is a short human-readable explanation
    of which condition fired, shown in the dashboard for judge Q&A."""
    persistent, industrial = bool(row["is_persistent"]), row["zone_type"] == "industrial"
    conf, frp, days = row["confidence_numeric"], row["frp"], row["persistence_days"]
    month = pd.Timestamp(row["acq_date"]).month

    if industrial and persistent and conf >= 60 and frp >= config.FRP_INDUSTRIAL_MIN:
        return "Industrial Fire", f"industrial zone + persistent {days}d + conf {conf:.0f} + FRP {frp:.1f}MW"
    if industrial and not persistent and conf >= 50:
        return "Industrial Flare / Transient Activity", f"industrial zone but only active {days}d, conf {conf:.0f}"
    if persistent and not industrial and frp >= config.FRP_INDUSTRIAL_MIN * 0.5:
        return "Persistent Non-Industrial Thermal Source", f"non-industrial + persistent {days}d + FRP {frp:.1f}MW"
    if not persistent and not industrial and conf < 50:
        if month in config.AGRI_BURN_MONTHS:
            return "Likely Agricultural Burning", f"low conf ({conf:.0f}) + single-day + burn-season month {month}"
        return "Likely Noise / Sun Glint", f"low conf ({conf:.0f}) + single-day + outside burn season"
    return "Unclassified / Needs Review", "borderline — no rule matched cleanly, review manually"


def classify(df: pd.DataFrame) -> pd.DataFrame:
    """Add `confidence_numeric`, `rule_label`, and `rule_reason` columns."""
    df = normalize_confidence(df)
    df[["rule_label", "rule_reason"]] = df.apply(_classify_row, axis=1, result_type="expand")
    return df
