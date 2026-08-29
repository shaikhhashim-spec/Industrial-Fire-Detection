"""Lightweight monitoring pipeline for secondary industrial corridors
beyond the flagship Jharkhand-Odisha belt (currently: Singrauli Coal &
Power Corridor) — detection + persistence only, no OSM industrial join and
no rule/ML classification, per the platform's staged-architecture
principle: the deep AI/OSM pipeline stays reserved for one flagship
region, and other corridors get the same "detect + track persistence"
treatment the national India-wide layer already uses (src/national/
pipeline.py), just scoped to a small bounding box instead of the whole
country, and without India-wide concerns like state-tagging.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import config
from src.firms.fetch import FirmsAuthError, _fetch_chunk
from src.ml.rules import normalize_confidence
from src.processing import cleaning
from src.processing.persistence import compute_persistence
from src.utils.event_id import add_event_ids

# Real named sites in the Sonbhadra-Singrauli belt (NTPC/NCL/Hindalco) used
# to seed realistic demo data — approximate public coordinates, not surveyed.
CORRIDOR_DEMO_SITES = [
    ("Singrauli Super Thermal Power Station", 24.10, 82.68),  # high-intensity continuous boiler heat
    ("NTPC Vindhyachal STPS", 24.098, 82.638),
    ("Anpara Thermal Power Station", 24.203, 82.747),
    ("NCL Jayant Coal Mine", 24.128, 82.679),
    ("NCL Nigahi Coal Mine", 24.153, 82.713),
    ("Hindalco Renukoot Smelter", 24.219, 83.033),
    ("Rihand Reservoir (Govind Ballabh Pant Sagar) shoreline", 24.052, 82.833),
]


def _corridor_risk(df: pd.DataFrame, window_days: int) -> pd.DataFrame:
    """Same simple FRP+confidence+persistence model as the national layer's
    _national_risk() (src/national/pipeline.py) — no industrial-proximity
    component, since that requires the OSM join this pipeline skips."""
    df = df.copy()
    w = config.NATIONAL_RISK_WEIGHTS
    window_days = window_days or config.NATIONAL_DAY_RANGE
    persistence_score = (df["persistence_days"] / max(window_days, 1) * 100).clip(upper=100)
    frp_score = (df["frp"] / config.FRP_HIGH_MIN * 100).clip(upper=100)
    conf_score = df["confidence_numeric"].clip(lower=0, upper=100)
    total = persistence_score * w["persistence"] + frp_score * w["frp"] + conf_score * w["confidence"]
    df["risk_score"] = total.clip(lower=0, upper=100).round(1)

    def _level(score):
        for lo, hi, label in config.RISK_LEVELS:
            if lo <= score <= hi:
                return label
        return "LOW"

    df["risk_level"] = df["risk_score"].apply(_level)
    return df


def _corridor_demo_hotspots(bbox: dict, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    today = pd.Timestamp.now().normalize()
    # Thermal power stations run continuous boilers -> higher, steadier FRP
    # and near-daily detections; everything else (mines/smelter/reservoir)
    # gets the more variable, moderate profile.
    power_stations = {"Singrauli Super Thermal Power Station", "NTPC Vindhyachal STPS", "Anpara Thermal Power Station"}

    rows = []
    for name, lat, lon in CORRIDOR_DEMO_SITES:
        is_power_station = name in power_stations
        n_days = int(rng.integers(24, 30)) if is_power_station else int(rng.integers(8, 20))
        frp_lo, frp_hi = (9.0, 22.0) if is_power_station else (2.0, 12.0)
        conf_p = [0.75, 0.2, 0.05] if is_power_station else [0.5, 0.35, 0.15]
        for d in range(n_days):
            rows.append({
                "latitude": lat + float(rng.normal(0, 0.004)), "longitude": lon + float(rng.normal(0, 0.004)),
                "acq_date": today - pd.Timedelta(days=d), "acq_time": int(rng.integers(0, 2359)),
                "satellite": str(rng.choice(["N20", "N21", "SNPP"])), "instrument": "VIIRS",
                "confidence": str(rng.choice(["h", "n", "l"], p=conf_p)),
                "frp": float(rng.uniform(frp_lo, frp_hi)), "daynight": str(rng.choice(["D", "N"])),
                "source": "VIIRS_NOAA20_NRT",
            })
    for _ in range(30):  # scattered background noise across the corridor
        rows.append({
            "latitude": float(rng.uniform(bbox["min_lat"], bbox["max_lat"])),
            "longitude": float(rng.uniform(bbox["min_lon"], bbox["max_lon"])),
            "acq_date": today - pd.Timedelta(days=int(rng.integers(0, 10))),
            "acq_time": int(rng.integers(0, 2359)), "satellite": "SNPP", "instrument": "VIIRS",
            "confidence": "n",
            "frp": float(rng.uniform(0.5, 4.0)), "daynight": str(rng.choice(["D", "N"])),
            "source": "VIIRS_SNPP_NRT",
        })
    return pd.DataFrame(rows)


def load_corridor_hotspots(bbox: dict, demo_mode: bool, api_key: str | None = None) -> tuple[pd.DataFrame, str]:
    if not demo_mode:
        key = api_key or config.FIRMS_API_KEY
        if key:
            area = f"{bbox['min_lon']},{bbox['min_lat']},{bbox['max_lon']},{bbox['max_lat']}"
            import datetime as dt
            today = dt.date.today()
            frames = []
            try:
                for source in config.NATIONAL_FIRMS_SOURCES:
                    chunk = _fetch_chunk(source, config.NATIONAL_DAY_RANGE, today.isoformat(), key, area=area)
                    if not chunk.empty:
                        chunk = chunk.copy()
                        chunk["source"] = source
                        frames.append(chunk)
                if frames:
                    df = pd.concat(frames, ignore_index=True)
                    df["acq_date"] = pd.to_datetime(df["acq_date"])
                    return df, "firms_live"
                print("[corridor.pipeline] FIRMS returned no rows, falling back to demo data")
            except FirmsAuthError as exc:
                print(f"[corridor.pipeline] FIRMS auth error: {exc}")
            except Exception as exc:
                print(f"[corridor.pipeline] FIRMS fetch failed: {exc}")

    return _corridor_demo_hotspots(bbox), "demo_data"


def run_corridor_pipeline(region_key: str, demo_mode: bool = False, api_key: str | None = None) -> dict:
    region_cfg = config.REGIONS[region_key]
    bbox = region_cfg["bbox"]

    raw_df, hotspot_source = load_corridor_hotspots(bbox, demo_mode, api_key)
    if raw_df.empty:
        raise RuntimeError(f"No hotspot data available for {region_cfg['name']} (live, cache, or demo).")

    clean_df, clean_report = cleaning.clean_hotspots(raw_df, bbox=bbox)
    if clean_df.empty:
        raise RuntimeError(f"All rows for {region_cfg['name']} were dropped during cleaning.")

    clean_df = normalize_confidence(clean_df)
    window_days = config.NATIONAL_DAY_RANGE if hotspot_source == "firms_live" else config.FIRMS_TOTAL_DAYS
    min_days = config.NATIONAL_PERSISTENCE_MIN_DAYS if hotspot_source == "firms_live" else config.PERSISTENCE_MIN_DAYS
    clean_df = compute_persistence(clean_df, min_days=min_days)
    clean_df = _corridor_risk(clean_df, window_days=window_days)

    events = (
        clean_df.groupby("grid_cell")
        .agg(
            latitude=("latitude", "mean"), longitude=("longitude", "mean"),
            observation_count=("frp", "size"), avg_frp=("frp", "mean"), max_frp=("frp", "max"),
            avg_confidence=("confidence_numeric", "mean"),
            persistence_days=("persistence_days", "max"), is_persistent=("is_persistent", "max"),
            risk_score=("risk_score", "max"), risk_level=("risk_level", "max"),
            satellites=("satellite", lambda s: sorted(set(s))),
        )
        .reset_index()
    )
    events = add_event_ids(events)

    return {
        "detail_df": clean_df, "events_df": events,
        "hotspot_source": hotspot_source, "clean_report": clean_report,
        "n_observations": len(clean_df), "n_events": len(events),
        "region_name": region_cfg["name"], "bbox": bbox,
        "persistence_window_days": window_days,
    }
