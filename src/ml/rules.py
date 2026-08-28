"""Rule-based classifier (v1) — explainable by construction. Every label
comes with a reason string and a short evidence list, and is the "weak
label" the ML layer (src/ml/train.py) is trained against and validated
with, NOT a ground-truth determination of what actually caused a detection.

Thresholds are PROTOTYPE/OPERATIONAL PARAMETERS calibrated against real
FIRMS data pulled for this region+window (see config.py) — not a
scientifically established fire-detection standard.
"""
from __future__ import annotations

import pandas as pd

import config

_VIIRS_CONF_MAP = {"l": 30, "n": 60, "h": 90}


def normalize_confidence(df: pd.DataFrame) -> pd.DataFrame:
    """VIIRS reports confidence as l/n/h; MODIS reports 0-100. Normalize
    both to a single 0-100 scale so downstream thresholds are consistent."""
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


def _classify_row(row) -> tuple[str, str, str]:
    """Return (label, reason, evidence) — evidence is a '|'-joined list of
    short factual statements shown in the investigation panel."""
    persistent, industrial = bool(row["is_persistent"]), row.get("zone_type") == "industrial"
    conf, frp, days = row["confidence_numeric"], row["frp"], row["persistence_days"]
    month = pd.Timestamp(row["acq_date"]).month
    ind_dist = row.get("industrial_distance_km")

    # Real OSM-polygon-backed landcover context (src/geospatial/landcover.py)
    # when available; all default to "no signal" (not "confirmed absent")
    # when the columns are missing entirely, e.g. Overpass was unavailable
    # or a test fixture doesn't provide them — the classification below then
    # falls back to exactly its old burn-season-month-only behavior.
    in_agri_zone = bool(row.get("in_agricultural_zone", False))
    forest_dist = row.get("forest_distance_km")
    near_forest = pd.notna(forest_dist) and forest_dist <= config.FOREST_NEAR_KM
    water_dist = row.get("water_distance_km")
    near_water = pd.notna(water_dist) and water_dist <= config.WATER_NEAR_KM

    evidence = []
    if conf >= config.CONF_INDUSTRIAL_FIRE_MIN:
        evidence.append(f"High satellite confidence ({conf:.0f}/100)")
    elif conf >= config.CONF_FLARE_MIN:
        evidence.append(f"Moderate satellite confidence ({conf:.0f}/100)")
    else:
        evidence.append(f"Low satellite confidence ({conf:.0f}/100)")
    if persistent:
        evidence.append(f"Active on {days} of the last {config.PERSISTENCE_DEFAULT_WINDOW_DAYS} days")
    else:
        evidence.append(f"Active on {days} day(s) so far — below the persistence bar")
    evidence.append(f"FRP {frp:.1f} MW ({'above' if frp >= config.FRP_INDUSTRIAL_MIN else 'below'} the notable-heat baseline)")
    if industrial:
        loc = f" ({ind_dist:.2f} km from center)" if pd.notna(ind_dist) else ""
        evidence.append(f"Located within a mapped industrial/mining zone{loc}")
    elif pd.notna(ind_dist):
        evidence.append(f"Nearest industrial/mining zone is {ind_dist:.1f} km away")
    if in_agri_zone:
        evidence.append("Located within a mapped agricultural (farmland/orchard) zone")
    if near_forest:
        evidence.append(f"Within {forest_dist:.2f} km of mapped forest")
    if near_water:
        evidence.append(f"Within {water_dist:.2f} km of a mapped water body — a known sun-glint false-positive source")

    def _r(label, reason):
        return label, reason, "|".join(evidence)

    if industrial and persistent and conf >= config.CONF_INDUSTRIAL_FIRE_MIN and frp >= config.FRP_INDUSTRIAL_MIN:
        return _r("Likely Industrial Fire", f"industrial zone + persistent {days}d + conf {conf:.0f} + FRP {frp:.1f}MW")
    if industrial and persistent:
        return _r("Persistent Industrial Activity", f"industrial zone + persistent {days}d, below the fire bar (conf {conf:.0f}, FRP {frp:.1f}MW)")
    if industrial and not persistent and conf >= config.CONF_FLARE_MIN:
        return _r("Transient Industrial Flare", f"industrial zone but only active {days}d, conf {conf:.0f}")
    if persistent and not industrial:
        return _r("Persistent Non-Industrial Thermal Source", f"non-industrial + persistent {days}d + FRP {frp:.1f}MW")
    if not persistent and not industrial:
        if in_agri_zone or month in config.AGRI_BURN_MONTHS:
            basis = "mapped agricultural zone" if in_agri_zone else f"burn-season month {month}"
            return _r("Likely Agricultural Burning", f"conf ({conf:.0f}) + single-day + {basis}")
        if near_water and conf < config.CONF_INDUSTRIAL_FIRE_MIN:
            return _r("Sun Glint / False Positive", f"low/moderate conf ({conf:.0f}) + single-day + near mapped water ({water_dist:.2f}km)")
        if conf < 50:
            return _r("Sun Glint / False Positive", f"low conf ({conf:.0f}) + single-day + outside burn season")
        if near_forest:
            return _r("Likely Wildfire", f"conf ({conf:.0f}) + single-day + near/within mapped forest ({forest_dist:.2f}km)")
        return _r("Likely Wildfire", f"conf ({conf:.0f}) + single-day + non-industrial + outside burn season")
    return _r("Requires Verification", "borderline — no rule matched cleanly, review manually")


def classify(df: pd.DataFrame) -> pd.DataFrame:
    """Add `confidence_numeric`, `rule_label`, `rule_reason`, `rule_evidence`."""
    df = normalize_confidence(df)
    df[["rule_label", "rule_reason", "rule_evidence"]] = df.apply(_classify_row, axis=1, result_type="expand")
    return df
