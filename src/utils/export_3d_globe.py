"""Export pipeline detections and risk scores into the Holo-View-Maker 3D Globe format.

Transforms regional (detail_gdf, cluster_df) and national (detail_df, events_df)
detections into the `ThermalEvent` JSON schema expected by the React + MapLibre
3D globe application in `holo-view-maker` (embedded in the Streamlit app's
"3D Holo Globe" page).
"""
from __future__ import annotations

import gzip
import json
import math
import os
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

import config

CATEGORY_VALID_SET = {
    "Likely Industrial Fire",
    "Persistent Non-Industrial Thermal Source",
    "Transient Industrial Flare",
    "Likely Agricultural Burning",
    "Sun Glint / False Positive",
    "Likely Wildfire",
    "Persistent Industrial Activity",
    "Requires Verification",
}

DEFAULT_OUTPUT_PUBLIC = config.BASE_DIR / "holo-view-maker" / "public" / "data" / "events.json"
DEFAULT_OUTPUT_DIST = config.OUTPUT_DIR / "holo_events.json"


_THERMAL_ALIASES = {
    "N": "VIIRS S-NPP", "S-NPP": "VIIRS S-NPP", "VIIRS_SNPP_NRT": "VIIRS S-NPP",
    "N20": "VIIRS NOAA-20", "NOAA-20": "VIIRS NOAA-20", "VIIRS_NOAA20_NRT": "VIIRS NOAA-20",
    "N21": "VIIRS NOAA-21", "NOAA-21": "VIIRS NOAA-21", "VIIRS_NOAA21_NRT": "VIIRS NOAA-21",
    "AQUA": "MODIS Aqua", "AQUA (MODIS)": "MODIS Aqua",
    "TERRA": "MODIS Terra", "TERRA (MODIS)": "MODIS Terra",
    **{s.upper(): s for s in ("VIIRS S-NPP", "VIIRS NOAA-20", "VIIRS NOAA-21", "MODIS Aqua", "MODIS Terra")},
}


def _thermal_day(value: Any) -> int | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value).toordinal()
    except ValueError:
        return None


def _thermal_group(row: dict) -> str | None:
    satellite = _THERMAL_ALIASES.get(str(row.get("satellite") or "").strip().upper())
    if not satellite or row.get("daynight") not in ("D", "N"):
        return None
    instrument = "VIIRS" if satellite.startswith("VIIRS") else "MODIS"
    if row.get("instrument") and str(row["instrument"]).strip().upper() != instrument:
        return None
    return f"{satellite}|{instrument}|{row['daynight']}"


def analyze_thermal_change(event: dict | None) -> dict[str, Any]:
    """Offline mirror of site/thermal-change.mjs; cross-language parity is tested.

    Unlike risk/anomaly.py's latest-row z-score and row-count trend window,
    this uses a median of daily peaks, excludes the entire current day and
    requires matching satellite/instrument/day-night groups. Observation days
    are prior days, not detections. Gaps never enter FRP arithmetic as zero.
    Thresholds are screening heuristics, not statistical or fire confirmation.
    """
    result = dict(status="insufficient_history", label="Insufficient history", baselineFrp=None,
                  currentFrp=None, changePercent=None, observationDays=0, gaps=0,
                  limitations=["Thermal change is a screening signal, not confirmation of fire or its cause.",
                               "Cloud, overpass and pixel coverage can change daily peaks; gaps are not zero heat."],
                  reasons=[], priorityPoints=0)

    def fail(reason):
        result["reasons"].append(reason)
        return result

    event = event or {}
    current_day = _thermal_day(event.get("acqDate"))
    if current_day is None:
        return fail("A valid current acquisition date is required.")
    if event.get("historyTruncated"):
        return fail("History was truncated; complete daily coverage is unavailable.")
    daily: dict[int, dict[str, float]] = {}
    unusable_days = set()
    invalid = unknown = unobserved = current_invalid = False
    first = current_day
    history = event.get("history")
    for row in history if isinstance(history, list) else []:
        row = row if isinstance(row, dict) else {}
        day = _thermal_day(row.get("date"))
        if day is None:
            invalid = True
            continue
        if day > current_day or day < current_day - 30:
            continue
        first = min(first, day)
        key, frp = _thermal_group(row), row.get("frp")
        marker = row.get("frpObserved")
        observed = (marker is None or marker is True) and (frp != 0 or marker is True)
        usable = isinstance(frp, (int, float)) and not isinstance(frp, bool) and math.isfinite(frp) and frp >= 0 and not row.get("synthetic") and observed
        if not usable or not key:
            unusable_days.add(day)
            invalid |= not usable
            unknown |= not bool(key)
            unobserved |= not observed
            current_invalid |= day == current_day
            continue
        groups = daily.setdefault(day, {})
        groups[key] = max(groups.get(key, -math.inf), frp)
    if invalid:
        result["limitations"].append("Invalid or synthetic history measurements were excluded.")
    if unknown:
        result["limitations"].append("History lacks reliable satellite/instrument/day-night metadata.")
    if unobserved:
        result["limitations"].append("Unobserved FRP and legacy zeros without measurement provenance are excluded.")
    result["gaps"] = current_day - first
    current = daily.get(current_day)
    if not current or current_invalid:
        return fail("Current-day observations with reliable sensor/pass metadata are required; the event window peak is not current FRP.")
    # Match JavaScript rounding (including negative ties) rather than banker's rounding.
    def rounded(value):
        return value if abs(value) >= 1e15 else math.floor((value + 2.220446049250313e-16) * 10 + 0.5) / 10

    current_peak = max(current.values())
    result["currentFrp"] = rounded(current_peak)
    peaks = [max(groups[key] for key in current) for day, groups in daily.items()
             if day < current_day and day not in unusable_days and current.keys() <= groups.keys()]
    result["observationDays"] = len(peaks)
    result["gaps"] -= len(peaks)
    if result["gaps"]:
        result["limitations"].append("Some calendar days lack comparable observations.")
    if len(peaks) < 3:
        return fail("At least three prior observation days with matching sensor/pass coverage are required.")
    peaks.sort()
    middle = len(peaks) // 2
    baseline = peaks[middle] if len(peaks) % 2 else peaks[middle - 1] / 2 + peaks[middle] / 2
    result["baselineFrp"] = rounded(baseline)
    if baseline <= 0:
        return fail("A positive baseline is required for a percentage comparison.")
    delta = current_peak - baseline
    percent = delta / baseline * 100
    if not math.isfinite(percent):
        return fail("FRP range prevents a finite percentage comparison.")
    result["changePercent"] = rounded(percent)
    result["status"] = "elevated" if percent >= 50 and delta >= 5 else "reduced" if percent <= -100 / 3 and delta <= -5 else "stable"
    result["label"] = {"elevated": "Elevated thermal output", "reduced": "Reduced thermal output",
                       "stable": "Recurring thermal activity; no substantial change"}[result["status"]]
    result["priorityPoints"] = 10 if result["status"] == "elevated" else 0
    result["reasons"].append("Current daily peak compared with the median of prior daily peaks using matching sensor/pass coverage.")
    return result


def _observation_history(group: pd.DataFrame) -> list[dict[str, Any]]:
    """Keep all rows in 30 prior days plus current, never the last 10/14 rows.

    Raw provenance avoids the display normalizer's invented S-NPP default and
    makes missing FRP null, not a zero. No aggregate/fallback peak is a history row.
    """
    dates = pd.to_datetime(group["acq_date"], errors="coerce")
    latest = dates.max()
    if pd.isna(latest):
        return []
    group = group.loc[dates >= latest.normalize() - pd.Timedelta(days=30)]
    history = []
    for _, row in group.iterrows():
        stamp = pd.to_datetime(row["acq_date"], errors="coerce")
        marker = row.get("frpObserved")
        observed = bool(marker) if pd.notna(marker) and marker in (True, False, 0, 1) else None
        frp = row.get("frp")
        if observed is False or (frp is not None and pd.notna(frp) and frp == 0 and observed is not True):
            frp = None
        observation = {"date": str(stamp.date()), "frp": frp, "frpObserved": observed,
                       "confidence": row.get("confidence_numeric"),
                       **{key: row.get(key) for key in ("satellite", "instrument", "daynight", "acq_time", "latitude", "longitude")}}
        history.append(_json_safe(observation))
    return history


def _normalize_category(label: Any) -> str:
    if not label or pd.isna(label):
        return "Requires Verification"
    s = str(label).strip()
    if s in CATEGORY_VALID_SET:
        return s
    s_lower = s.lower()
    if "industrial fire" in s_lower:
        return "Likely Industrial Fire"
    if "flare" in s_lower:
        return "Transient Industrial Flare"
    if "agricultural" in s_lower or "stubble" in s_lower:
        return "Likely Agricultural Burning"
    if "wildfire" in s_lower or "forest" in s_lower:
        return "Likely Wildfire"
    if "glint" in s_lower or "false" in s_lower:
        return "Sun Glint / False Positive"
    if "non-industrial" in s_lower:
        return "Persistent Non-Industrial Thermal Source"
    if "industrial activity" in s_lower or "industrial" in s_lower:
        return "Persistent Industrial Activity"
    return "Requires Verification"


def _normalize_risk_level(score: float, level_str: Any = None) -> str:
    if level_str and str(level_str).upper() in ("LOW", "MODERATE", "HIGH", "CRITICAL"):
        return str(level_str).upper()
    if score >= 76:
        return "CRITICAL"
    if score >= 51:
        return "HIGH"
    if score >= 26:
        return "MODERATE"
    return "LOW"


def _normalize_satellite(sat: Any) -> str:
    """Accepts either a raw FIRMS source tag ("MODIS_NRT", "VIIRS_NOAA20_NRT")
    or the already-humanized short name national/context.py's `_sat_name`
    produces ("Aqua", "N20", ...) — evidence.satellites carries the latter,
    and both forms have to map to the same globe-facing label or MODIS
    detections silently fall through to the VIIRS S-NPP default."""
    s = str(sat).upper() if sat and pd.notna(sat) else ""
    if "NOAA21" in s or "NOAA-21" in s or "N21" in s:
        return "VIIRS NOAA-21"
    if "NOAA20" in s or "NOAA-20" in s or "N20" in s:
        return "VIIRS NOAA-20"
    if "AQUA" in s or "MYD" in s:
        return "MODIS Aqua"
    if "TERRA" in s or "MODIS" in s:
        # "MODIS_NRT" alone (the combined source tag) can't distinguish the
        # two satellites, so it defaults to Terra rather than dropping the
        # detection's instrument entirely.
        return "MODIS Terra"
    return "VIIRS S-NPP"


def _normalize_status(row: pd.Series | dict) -> str:
    status = str(row.get("status", "")).upper()
    if status in ("CRITICAL", "HIGH RISK", "PERSISTENT", "RECURRING", "NEW"):
        return status
    risk_lvl = str(row.get("risk_level", "")).upper()
    if risk_lvl == "CRITICAL":
        return "CRITICAL"
    if risk_lvl == "HIGH":
        return "HIGH RISK"
    persist_days = float(row.get("persistence_days", row.get("persistence_30d", 0)) or 0)
    if persist_days >= 14:
        return "PERSISTENT"
    if persist_days >= 4:
        return "RECURRING"
    return "NEW"


# FIRMS reports VIIRS by a one-letter code ("N" alone reads like a typo, but it is
# Suomi NPP); MODIS already says Aqua or Terra.
_SATELLITE_LABELS = {"N": "S-NPP", "N20": "NOAA-20", "N21": "NOAA-21", "Aqua": "Aqua (MODIS)", "Terra": "Terra (MODIS)"}


def _national_summary(events_df: pd.DataFrame, detail_df: pd.DataFrame | None) -> dict[str, Any]:
    """The run-level counts the dashboard's Overview shows, written into the data
    file so a static page can show the same numbers without the raw observations."""
    out: dict[str, Any] = {}
    if "is_persistent" in events_df.columns:
        out["persistentSources"] = int(events_df["is_persistent"].sum())
    if detail_df is not None and not detail_df.empty:
        out["observations"] = int(len(detail_df))
        if "state" in detail_df.columns:
            out["statesWithActivity"] = int(detail_df["state"].nunique())
        if "satellite" in detail_df.columns:
            names = detail_df["satellite"].dropna().astype(str).unique()
            out["satellites"] = sorted(_SATELLITE_LABELS.get(s, s) for s in names)
    return out


def _as_int(value: Any, default: int) -> int:
    """A cached cluster_summary.csv carries NaN wherever a column did not apply
    to that row, and int(nan) raises. Anything unusable falls back."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return int(round(number)) if math.isfinite(number) else default


def _qualifies_for_plume(category: Any, frp: float) -> bool:
    return frp >= config.PLUME_FRP_MIN_MW or category in config.PLUME_CATEGORIES


def _attach_plume(event: dict[str, Any]) -> None:
    """Downwind smoke/gas dispersion cone for a high-intensity event, from
    live wind at its location. A visual heuristic (see src/utils/wind.py's
    module docstring), not a scientific atmospheric dispersion model."""
    from src.utils import wind as wind_utils

    lat, lon, frp = event["latitude"], event["longitude"], event["frp"]
    wind_data = wind_utils.get_wind(lat, lon)
    bearing = wind_utils.downwind_bearing(wind_data["direction_deg"])
    cone_length_km = wind_utils.dispersion_cone_length_km(wind_data["speed_kmh"], frp)
    polygon_latlon = wind_utils.dispersion_cone_polygon(
        lat, lon, wind_data["direction_deg"], wind_data["speed_kmh"], frp,
    )
    event["plume"] = {
        "source": wind_data.get("source", "unknown"),
        "observedAt": wind_data.get("observed_at"),
        "estimated": True,
        "windSpeedKmh": round(wind_data["speed_kmh"], 1),
        "windDirectionDeg": round(wind_data["direction_deg"], 0),
        "downwindBearingDeg": round(bearing, 0),
        "coneLengthKm": round(cone_length_km, 1),
        # GeoJSON coordinate order (lon, lat) — dispersion_cone_polygon returns (lat, lon).
        "polygon": [[lon_, lat_] for lat_, lon_ in polygon_latlon],
    }
    from src.utils.spread import calculate_spread_potential

    spread = calculate_spread_potential(wind_data, frp)
    if spread is not None:
        event["spreadPotential"] = spread


def transform_regional_to_holo_events(
    detail_gdf: gpd.GeoDataFrame | pd.DataFrame | None,
    cluster_df: pd.DataFrame | None,
) -> list[dict[str, Any]]:
    """Convert regional cluster & detail dataframes into Holo-View 3D events."""
    if cluster_df is None or cluster_df.empty:
        return []

    # Map detail history by grid_cell if available
    history_by_cell: dict[str, list[dict[str, Any]]] = {}
    brightness_by_cell: dict[str, float] = {}
    daynight_by_cell: dict[str, str] = {}
    latest_date_by_cell: dict[str, str] = {}

    if detail_gdf is not None and not detail_gdf.empty:
        gdf_sorted = detail_gdf.sort_values("acq_date", ascending=True)
        for cell, group in gdf_sorted.groupby("grid_cell"):
            cell_str = str(cell)
            history_by_cell[cell_str] = _observation_history(group)
            brightness_by_cell[cell_str] = float(group["brightness"].mean()) if "brightness" in group.columns else 328.0
            daynight_by_cell[cell_str] = str(group["daynight"].iloc[-1]) if "daynight" in group.columns and pd.notna(group["daynight"].iloc[-1]) else "D"
            if "acq_date" in group.columns:
                latest_date_by_cell[cell_str] = str(pd.to_datetime(group["acq_date"].iloc[-1]).date())

    events: list[dict[str, Any]] = []
    for _, row in cluster_df.iterrows():
        cell = str(row.get("grid_cell", ""))
        eid = str(row.get("event_id", cell or f"TI-{len(events)+1:04d}"))
        lat = float(row.get("latitude", 0.0))
        lon = float(row.get("longitude", 0.0))
        category = _normalize_category(row.get("dominant_label", row.get("rule_label", row.get("classification", "Requires Verification"))))
        risk_score = float(row.get("risk_score", 0.0))
        risk_level = _normalize_risk_level(risk_score, row.get("risk_level"))
        frp = float(row.get("max_frp", row.get("avg_frp", row.get("frp", 12.0))))
        persist_col = [c for c in row.index if c.startswith("persistence_") and c.endswith("d")]
        raw_persist = row.get(persist_col[0]) if persist_col else row.get("persistence_days")
        persist_days = _as_int(raw_persist, _as_int(row.get("persistence_days"), 1))
        detection_count = _as_int(row.get("detection_count"), persist_days)
        status = _normalize_status(row)

        region_desc = config.REGION_NAME
        zone_type = str(row.get("zone_type", ""))
        zone_kind = str(row.get("zone_kind", ""))
        if zone_kind and zone_kind != "nan" and zone_kind != "?":
            region_desc = f"{zone_kind.title()} Cluster ({config.REGION_NAME})"
        elif zone_type and zone_type != "nan" and zone_type != "?":
            region_desc = f"{zone_type.title()} Zone ({config.REGION_NAME})"

        hist = history_by_cell.get(cell, [])

        acq_date = latest_date_by_cell.get(cell, str(pd.to_datetime(row.get("last_detected", "2026-08-30")).date()))
        brightness = brightness_by_cell.get(cell, float(row.get("brightness", 325.0)))
        daynight = daynight_by_cell.get(cell, "N" if "N" in str(row.get("daynight", "")) else "D")
        sats = row.get("satellites", [])
        satellite = _normalize_satellite(sats[0] if isinstance(sats, (list, tuple)) and sats else str(sats))

        events.append({
            "id": eid,
            "region": region_desc,
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
            "category": category,
            "riskScore": _as_int(risk_score, 0),
            "riskLevel": risk_level,
            "frp": round(frp, 1),
            "brightness": _as_int(brightness, 325),
            "confidence": _as_int(row.get("avg_confidence"), 85),
            "persistenceDays": persist_days,
            "detectionCount": detection_count,
            "satellite": satellite,
            "daynight": "N" if daynight == "N" else "D",
            "status": status,
            "acqDate": acq_date,
            "history": hist,
        })

    for event in events:
        event["thermalChange"] = analyze_thermal_change(event)
    return sorted(events, key=lambda x: x["riskScore"], reverse=True)


def transform_national_to_holo_events(
    detail_df: pd.DataFrame | None,
    events_df: pd.DataFrame | None,
) -> list[dict[str, Any]]:
    """Convert national events & detail dataframes into Holo-View 3D events."""
    if events_df is None or events_df.empty:
        return []

    history_by_cell: dict[str, list[dict[str, Any]]] = {}
    if detail_df is not None and not detail_df.empty and "acq_date" in detail_df.columns:
        df_sorted = detail_df.sort_values("acq_date", ascending=True)
        for cell, group in df_sorted.groupby("grid_cell"):
            cell_str = str(cell)
            history_by_cell[cell_str] = _observation_history(group)

    events: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for _, row in events_df.iterrows():
        cell = str(row.get("grid_cell", ""))
        eid = str(row.get("event_id", cell or f"NAT-{len(events)+1:04d}"))
        # 6-hex event ids collide at national volume; keep every event addressable
        base, n = eid, 2
        while eid in seen_ids:
            eid, n = f"{base}-{n}", n + 1
        seen_ids.add(eid)
        lat = float(row.get("latitude", 0.0))
        lon = float(row.get("longitude", 0.0))
        state = row.get("state")
        state_clean = str(state) if isinstance(state, str) and state and state != "nan" else "India"

        is_persist = bool(row.get("is_persistent", False))
        frp = float(row.get("max_frp", row.get("avg_frp", row.get("frp", 10.0))))
        risk_score = float(row.get("risk_score", 0.0))
        risk_level = _normalize_risk_level(risk_score, row.get("risk_level"))
        persist_days = int(row.get("persistence_days", 1))

        evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else None
        category = row.get("category")
        if not isinstance(category, str) or category not in CATEGORY_VALID_SET:
            # no open-source context available (reference data not built) —
            # fall back to the evidence-only heuristic
            if is_persist and frp > 12:
                category = "Persistent Industrial Activity"
            elif is_persist:
                category = "Persistent Non-Industrial Thermal Source"
            elif frp > 30:
                category = "Likely Industrial Fire"
            else:
                category = "Requires Verification"

        hist = history_by_cell.get(cell, [])

        place = row.get("place_name")
        place_ok = isinstance(place, str) and bool(place)
        region = f"{place}, {state_clean}" if place_ok else state_clean
        sats = (evidence or {}).get("satellites") or []
        facility = row.get("facility") if isinstance(row.get("facility"), dict) else None
        reasons = row.get("reasons")
        district = row.get("district")
        direction = row.get("place_dir")

        events.append({
            "id": eid,
            "region": region,
            "state": state_clean,
            "district": district if isinstance(district, str) and district else None,
            "place": {
                "name": place,
                "distanceKm": float(row.get("place_km", 0.0)),
                "direction": direction if isinstance(direction, str) else "",
            } if place_ok else None,
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
            "category": category,
            "riskScore": int(round(risk_score)),
            "riskLevel": risk_level,
            "frp": round(frp, 1),
            "brightness": int(round(float(row.get("brightness", 320.0)))),
            "confidence": int(round(float(row.get("avg_confidence", 80.0)))),
            "persistenceDays": int((evidence or {}).get("days", persist_days)),
            "detectionCount": int((evidence or {}).get("detections", row.get("observation_count", persist_days))),
            "satellite": _normalize_satellite(sats[0] if sats else row.get("satellite", "")),
            "satellites": [_normalize_satellite(s) for s in sats],
            "daynight": "N" if (evidence or {}).get("nightPasses", 0) > 0 else "D",
            "status": _normalize_status(row),
            "acqDate": (evidence or {}).get("lastSeen") or (hist[-1]["date"] if hist else ""),
            "facility": facility,
            "corroborated": bool(row.get("corroborated", True)),
            "reasons": list(reasons) if isinstance(reasons, (list, tuple)) else [],
            "evidence": evidence,
            # Why it is risky, whether the model agrees, and what to do next.
            "priority": int(row["priority"]) if pd.notna(row.get("priority")) else None,
            "riskFactors": list(row["risk_factors"]) if isinstance(row.get("risk_factors"), (list, tuple)) else [],
            "riskSummary": row.get("risk_summary") if isinstance(row.get("risk_summary"), str) else None,
            "actions": list(row["actions"]) if isinstance(row.get("actions"), (list, tuple)) else [],
            "model": row.get("model_check") if isinstance(row.get("model_check"), dict) else None,
            "history": hist,
        })

    for event in events:
        event["thermalChange"] = analyze_thermal_change(event)
    return sorted(events, key=lambda x: x["riskScore"], reverse=True)


def export_pipeline_events_for_holo_view(
    detail_gdf: gpd.GeoDataFrame | pd.DataFrame | None = None,
    cluster_df: pd.DataFrame | None = None,
    events_df: pd.DataFrame | None = None,
    national_detail_df: pd.DataFrame | None = None,
    destinations: list[Path | str] | None = None,
) -> list[dict[str, Any]]:
    """Main export entrypoint. Transmutes live or cached detections into 3D Holo format

    and saves to `holo-view-maker/public/data/events.json` and `output/holo_events.json`
    as `{"meta": {...}, "events": [...]}` — `meta.source` says where the globe's
    points came from (live FIRMS data, or a mix of live runs).
    """
    events: list[dict[str, Any]] = []
    sources: set[str] = set()
    national_live = events_df is not None and not events_df.empty

    # 1. Regional data, passed in or cached — only when there is no live
    #    national run: the national dataset already covers the belt, with the
    #    same open-source explanation for every point, and mixing in the belt's
    #    separately-classified cells would show two answers for one place.
    if national_live:
        pass
    elif cluster_df is not None and not cluster_df.empty:
        events.extend(transform_regional_to_holo_events(detail_gdf, cluster_df))
        sources.add("firms_live")
    elif config.CLASSIFIED_GEOJSON.exists() and (config.PROCESSED_DIR / "cluster_summary.csv").exists():
        try:
            g_df = gpd.read_file(config.CLASSIFIED_GEOJSON)
            c_df = pd.read_csv(config.PROCESSED_DIR / "cluster_summary.csv")
            events.extend(transform_regional_to_holo_events(g_df, c_df))
            sources.add("firms_live")
        except Exception as e:
            print(f"[export_3d_globe] failed to read cached regional data: {e}")

    # 2. Check national data if available
    if events_df is not None and not events_df.empty:
        nat_events = transform_national_to_holo_events(national_detail_df, events_df)
        sources.add("firms_live")
        # Avoid duplicate IDs
        existing_ids = {e["id"] for e in events}
        for ne in nat_events:
            if ne["id"] not in existing_ids:
                events.append(ne)

    # Live data only: with nothing real to export, keep the globe's last export
    # untouched rather than overwriting it with an empty or synthetic set.
    if not events:
        print("[export_3d_globe] no live events to export; leaving the previous export in place")
        return events

    # Sort descending by risk score
    events.sort(key=lambda x: x["riskScore"], reverse=True)

    # Downwind smoke/gas dispersion cones for the highest-intensity events
    # only: a live wind lookup per event, capped so an export never turns
    # into dozens of sequential, mostly-uncached HTTP calls.
    qualifying = [e for e in events if _qualifies_for_plume(e["category"], e["frp"])]
    qualifying.sort(key=lambda x: x["frp"], reverse=True)
    for e in qualifying[:config.PLUME_MAX_CONES]:
        try:
            _attach_plume(e)
        except Exception as exc:
            print(f"[export_3d_globe] plume skipped for {e['id']}: {exc}")

    source = sources.pop() if len(sources) == 1 else ("mixed" if sources else "none")
    payload = _json_safe({
        "meta": {
            "source": source,
            "scope": "india" if national_live else "jharkhand_odisha",
            "generatedAt": pd.Timestamp.now(tz="UTC").isoformat(),
            "events": len(events),
            "windowDays": config.NATIONAL_HISTORY_DAYS,
            **(_national_summary(events_df, national_detail_df) if national_live else {}),
            "attribution": [
                "NASA FIRMS VIIRS and MODIS active fires",
                "© OpenStreetMap contributors (ODbL)",
                "WRI Global Power Plant Database (CC BY 4.0)",
                "GeoNames (CC BY 4.0)",
            ],
        },
        "events": events,
    })

    # Destination paths
    target_dests = [DEFAULT_OUTPUT_PUBLIC, DEFAULT_OUTPUT_DIST]
    if destinations:
        target_dests = [Path(d) for d in destinations]

    # Save to all destinations
    for dest in target_dests:
        dest_path = Path(dest)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    if not destinations:  # the real globe export, not a test/temp destination
        _export_facilities_layer()
        _export_plumes_layer(events)
    return events


def _json_safe(obj: Any) -> Any:
    """NaN/inf → null, numpy scalars → Python — json.dumps would otherwise
    write a bare NaN, which the browser's JSON.parse rejects outright."""
    if obj is pd.NA or obj is pd.NaT:
        return None
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if hasattr(obj, "item") and not isinstance(obj, (str, bytes)):
        obj = obj.item()
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    return obj


FACILITIES_PUBLIC = config.BASE_DIR / "holo-view-maker" / "public" / "data" / "facilities.geojson"


def _export_facilities_layer() -> None:
    """Ship the open-source facility reference layer to the globe."""
    try:
        from src.national.context import facilities_geojson

        fc = facilities_geojson()
        if fc["features"]:
            FACILITIES_PUBLIC.write_text(json.dumps(_json_safe(fc), ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[export_3d_globe] facility layer export skipped: {e}")


PLUMES_PUBLIC = config.BASE_DIR / "holo-view-maker" / "public" / "data" / "plumes.geojson"


def _export_plumes_layer(events: list[dict[str, Any]]) -> None:
    """Standalone GeoJSON of the same dispersion cones already embedded on
    each qualifying event, for consumers that want the polygons without the
    rest of the event payload."""
    try:
        features = [
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [e["plume"]["polygon"]]},
                "properties": {
                    "eventId": e["id"],
                    "frp": e["frp"],
                    "riskLevel": e["riskLevel"],
                    "windSpeedKmh": e["plume"]["windSpeedKmh"],
                    "downwindBearingDeg": e["plume"]["downwindBearingDeg"],
                },
            }
            for e in events if e.get("plume")
        ]
        fc = {"type": "FeatureCollection", "features": features}
        PLUMES_PUBLIC.parent.mkdir(parents=True, exist_ok=True)
        PLUMES_PUBLIC.write_text(json.dumps(_json_safe(fc), ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[export_3d_globe] plumes layer export skipped: {e}")


def load_or_export_holo_events() -> list[dict[str, Any]]:
    """Loads currently exported 3D events from disk or generates and exports them if not yet created."""
    if DEFAULT_OUTPUT_PUBLIC.exists():
        try:
            data = json.loads(DEFAULT_OUTPUT_PUBLIC.read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                return data
            if isinstance(data, dict) and "events" in data:
                return data["events"]
        except Exception:
            pass

    if DEFAULT_OUTPUT_DIST.exists():
        try:
            data = json.loads(DEFAULT_OUTPUT_DIST.read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                return data
            if isinstance(data, dict) and data.get("events"):
                return data["events"]
        except Exception:
            pass

    return export_pipeline_events_for_holo_view()


def augment_thermal_snapshot(source: Path | str, destination: Path | str) -> Path:
    """Precompute copied feeds; refresh an existing destination gzip companion.

    The input remains byte-identical. JSON validation and compression finish
    before publication; each output is atomically replaced, JSON published last.
    """
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve() or (destination.exists() and source.samefile(destination)):
        raise ValueError("Thermal snapshot output must differ from the source feed")
    payload = json.loads(source.read_text(encoding="utf-8"))
    events = payload if isinstance(payload, list) else payload.get("events") if isinstance(payload, dict) else None
    if not isinstance(events, list) or not all(isinstance(event, dict) for event in events):
        raise ValueError("Expected an event array or a payload containing an events array")
    for event in events:
        event["thermalChange"] = analyze_thermal_change(event)
    body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
    companion = destination.with_suffix(".json.gz")
    if companion.exists() and (source.resolve() == companion.resolve() or source.samefile(companion)):
        raise ValueError("Thermal gzip output must differ from the source feed")
    compressed = gzip.compress(body, mtime=0) if companion.exists() else None
    destination.parent.mkdir(parents=True, exist_ok=True)
    if compressed is not None:
        _atomic_snapshot_bytes(companion, compressed)
    _atomic_snapshot_bytes(destination, body)
    return destination


def _atomic_snapshot_bytes(destination: Path, body: bytes) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as file:
            temporary = Path(file.name)
            file.write(body)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Precompute thermalChange on a copied event feed; no ingestion.")
    parser.add_argument("--thermal-input", type=Path, required=True)
    parser.add_argument("--thermal-output", type=Path, required=True)
    args = parser.parse_args()
    augment_thermal_snapshot(args.thermal_input, args.thermal_output)

