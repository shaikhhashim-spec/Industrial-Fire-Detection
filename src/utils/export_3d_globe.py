"""Export pipeline detections and risk scores into the Holo-View-Maker 3D Globe format.

Transforms regional (detail_gdf, cluster_df) and national (detail_df, events_df)
detections into the `ThermalEvent` JSON schema expected by the React + MapLibre
3D globe application in `holo-view-maker` (embedded in the Streamlit app's
"3D Holo Globe" page).
"""
from __future__ import annotations

import json
import math
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


def _as_int(value: Any, default: int) -> int:
    """A cached cluster_summary.csv carries NaN wherever a column did not apply
    to that row, and int(nan) raises. Anything unusable falls back."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return int(round(number)) if math.isfinite(number) else default


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
            hist = []
            for _, r in group.iterrows():
                acq_d = str(pd.to_datetime(r["acq_date"]).date()) if pd.notna(r.get("acq_date")) else "2026-08-30"
                frp_val = float(r.get("frp", 0.0))
                conf_val = float(r.get("confidence_numeric", 70.0))
                hist.append({
                    "date": acq_d,
                    "frp": round(frp_val, 1),
                    "confidence": round(conf_val, 1),
                })
            history_by_cell[cell_str] = hist[-14:] if len(hist) > 14 else hist
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
        if not hist:
            hist = [{
                "date": str(pd.to_datetime(row.get("last_detected", "2026-08-30")).date()),
                "frp": round(frp, 1),
                "confidence": 85.0,
            }]

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
            hist = []
            for _, r in group.iterrows():
                acq_d = str(pd.to_datetime(r["acq_date"]).date()) if pd.notna(r.get("acq_date")) else "2026-08-30"
                hist.append({
                    "date": acq_d,
                    "frp": round(float(r.get("frp", 0.0)), 1),
                    "confidence": round(float(r.get("confidence_numeric", 70.0)), 1),
                })
            history_by_cell[cell_str] = hist[-10:] if len(hist) > 10 else hist

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
        if not hist:
            hist = [{"date": (evidence or {}).get("lastSeen") or "", "frp": round(frp, 1), "confidence": 80.0}]

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
            "acqDate": (evidence or {}).get("lastSeen") or hist[-1]["date"],
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
    as `{"meta": {...}, "events": [...]}` — `meta.source` says honestly whether the
    globe is showing live FIRMS data or demo data.
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

    source = sources.pop() if len(sources) == 1 else ("mixed" if sources else "none")
    payload = _json_safe({
        "meta": {
            "source": source,
            "generatedAt": pd.Timestamp.now(tz="UTC").isoformat(),
            "events": len(events),
            "windowDays": config.NATIONAL_HISTORY_DAYS,
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
    return events


def _json_safe(obj: Any) -> Any:
    """NaN/inf → null, numpy scalars → Python — json.dumps would otherwise
    write a bare NaN, which the browser's JSON.parse rejects outright."""
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

