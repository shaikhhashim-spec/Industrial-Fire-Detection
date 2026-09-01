"""Export pipeline detections and risk scores into the Holo-View-Maker 3D Globe format.

Transforms regional (detail_gdf, cluster_df) and national (detail_df, events_df)
detections into the `ThermalEvent` JSON schema expected by the React + Three.js
3D globe application in `holo-view-maker`.
"""
from __future__ import annotations

import base64
import functools
import json
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

# Above this many simultaneous ground markers, the fixed-size halo rings
# start overlapping into an unreadable solid blob (each marker is a real
# beam + halo + core, not a lightweight point) — cap to the highest-risk
# subset instead, mirroring app.py's existing TIMELAPSE_MAX_POINTS pattern
# for the 2D map's timelapse layer.
MAX_RENDERED_GLOBE_EVENTS = 400

# Local Earth texture set bundled with holo-view-maker — reused here so the
# embedded globe below doesn't depend on live CDN fetches for its base
# rendering. Falls back to the existing CDN URLs if this folder is absent
# (e.g. a deployment that ships only the Python app).
_TEXTURES_DIR = config.BASE_DIR / "holo-view-maker" / "public" / "textures"
_COASTLINE_PATH = config.BASE_DIR / "holo-view-maker" / "public" / "geo" / "land-110m.geojson"


@functools.lru_cache(maxsize=None)
def _local_texture_data_uri(filename: str, mime: str) -> str | None:
    """Reads a bundled texture once per process and returns it as a data: URI, or None if unavailable."""
    path = _TEXTURES_DIR / filename
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


@functools.lru_cache(maxsize=None)
def _local_coastline_geojson() -> str | None:
    """Reads the bundled Natural Earth 110m land geojson once per process, or None if unavailable."""
    try:
        return _COASTLINE_PATH.read_text(encoding="utf-8")
    except OSError:
        return None


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
    s = str(sat).upper() if sat and pd.notna(sat) else ""
    if "NOAA20" in s or "NOAA-20" in s or "N20" in s:
        return "VIIRS NOAA-20"
    if "MODIS" in s:
        if "AQUA" in s or "MYD" in s:
            return "MODIS Aqua"
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
        persist_days = int(row.get(persist_col[0], row.get("persistence_days", 1))) if persist_col else int(row.get("persistence_days", 1))
        detection_count = int(row.get("detection_count", persist_days))
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
            "riskScore": int(round(risk_score)),
            "riskLevel": risk_level,
            "frp": round(frp, 1),
            "brightness": int(round(brightness)),
            "confidence": int(round(float(row.get("avg_confidence", 85.0)))),
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
    for _, row in events_df.iterrows():
        cell = str(row.get("grid_cell", ""))
        eid = str(row.get("event_id", cell or f"NAT-{len(events)+1:04d}"))
        lat = float(row.get("latitude", 0.0))
        lon = float(row.get("longitude", 0.0))
        state = str(row.get("state", "India National Watch"))
        state_clean = state if state and state != "nan" else "India"

        # National heuristic classification
        is_persist = bool(row.get("is_persistent", False))
        frp = float(row.get("max_frp", row.get("avg_frp", row.get("frp", 10.0))))
        risk_score = float(row.get("risk_score", 0.0))
        risk_level = _normalize_risk_level(risk_score, row.get("risk_level"))
        persist_days = int(row.get("persistence_days", 1))

        if state in ("Punjab", "Haryana") and frp < 15:
            category = "Likely Agricultural Burning"
        elif is_persist and frp > 12:
            category = "Persistent Industrial Activity"
        elif is_persist:
            category = "Persistent Non-Industrial Thermal Source"
        elif frp > 30:
            category = "Likely Industrial Fire"
        elif state in ("Uttarakhand", "Himachal Pradesh", "Odisha") and frp > 15:
            category = "Likely Wildfire"
        else:
            category = "Requires Verification"

        hist = history_by_cell.get(cell, [])
        if not hist:
            hist = [{"date": "2026-08-30", "frp": round(frp, 1), "confidence": 80.0}]

        events.append({
            "id": eid,
            "region": f"{state_clean} Hotspot Zone",
            "latitude": round(lat, 4),
            "longitude": round(lon, 4),
            "category": category,
            "riskScore": int(round(risk_score)),
            "riskLevel": risk_level,
            "frp": round(frp, 1),
            "brightness": int(round(float(row.get("brightness", 320.0)))),
            "confidence": int(round(float(row.get("avg_confidence", 80.0)))),
            "persistenceDays": persist_days,
            "detectionCount": int(row.get("observation_count", persist_days)),
            "satellite": _normalize_satellite(row.get("satellite", "VIIRS S-NPP")),
            "daynight": "D",
            "status": _normalize_status(row),
            "acqDate": hist[-1]["date"] if hist else "2026-08-30",
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

    and saves to `holo-view-maker/public/data/events.json` and `output/holo_events.json`.
    """
    events: list[dict[str, Any]] = []

    # 1. Check if regional data passed or cached
    if cluster_df is not None and not cluster_df.empty:
        events.extend(transform_regional_to_holo_events(detail_gdf, cluster_df))
    elif config.CLASSIFIED_GEOJSON.exists() and (config.PROCESSED_DIR / "cluster_summary.csv").exists():
        try:
            c_df = pd.read_csv(config.PROCESSED_DIR / "cluster_summary.csv")
            g_df = gpd.read_file(config.CLASSIFIED_GEOJSON)
            events.extend(transform_regional_to_holo_events(g_df, c_df))
        except Exception as e:
            print(f"[export_3d_globe] failed to read cached regional data: {e}")

    # 2. Check national data if available
    if events_df is not None and not events_df.empty:
        nat_events = transform_national_to_holo_events(national_detail_df, events_df)
        # Avoid duplicate IDs
        existing_ids = {e["id"] for e in events}
        for ne in nat_events:
            if ne["id"] not in existing_ids:
                events.append(ne)

    # 3. If still empty, fall back to sample/demo generation to guarantee ready 3D visualization
    if not events:
        try:
            from src import pipeline
            info = pipeline.run_pipeline(demo_mode=True)
            events = transform_regional_to_holo_events(info.get("detail_gdf"), info.get("cluster_df"))
        except Exception as e:
            print(f"[export_3d_globe] fallback demo pipeline run failed: {e}")

    # Sort descending by risk score
    events.sort(key=lambda x: x["riskScore"], reverse=True)

    # Destination paths
    target_dests = [DEFAULT_OUTPUT_PUBLIC, DEFAULT_OUTPUT_DIST]
    if destinations:
        target_dests = [Path(d) for d in destinations]

    # Save to all destinations
    for dest in target_dests:
        dest_path = Path(dest)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_text(json.dumps(events, indent=2), encoding="utf-8")

    return events


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
        except Exception:
            pass

    return export_pipeline_events_for_holo_view()


def generate_embedded_3d_globe_html(
    events: list[dict[str, Any]] | None = None,
    color_by: str = "category",
    auto_rotate: bool = True,
    min_risk: int = 0,
    selected_event_id: str | None = None,
) -> str:
    """Generates a complete, self-contained photorealistic 3D WebGL Globe HTML/JS application
    powered by Three.js that renders directly inside Streamlit without external dev servers.
    Features deep zoom revealing ultra-clear 2D-like high-resolution satellite imagery and ground GIS details.
    """
    if events is None:
        events = load_or_export_holo_events()

    all_filtered_events = [e for e in events if e.get("riskScore", 0) >= min_risk]
    total_filtered_count = len(all_filtered_events)
    hidden_count = 0
    if total_filtered_count > MAX_RENDERED_GLOBE_EVENTS:
        # Capping by risk score alone collapses onto whichever single region
        # scores highest (e.g. the Jharkhand-Odisha belt, which runs the full
        # AI pipeline and so scores systematically higher than the lighter
        # national heuristic) — every other region's markers would vanish
        # even though real detections exist there too. Bucket by a coarse
        # lat/lon grid first so every populated region keeps a fair share,
        # then cap to the target count from that geographically-spread pool.
        buckets: dict[tuple[int, int], list[dict]] = {}
        for e in all_filtered_events:
            key = (round(e.get("latitude", 0.0) / 2), round(e.get("longitude", 0.0) / 2))
            buckets.setdefault(key, []).append(e)
        per_bucket_cap = max(1, MAX_RENDERED_GLOBE_EVENTS // max(1, len(buckets)) + 2)
        diversified: list[dict] = []
        for bucket_events in buckets.values():
            bucket_events.sort(key=lambda e: e.get("riskScore", 0), reverse=True)
            diversified.extend(bucket_events[:per_bucket_cap])
        diversified.sort(key=lambda e: e.get("riskScore", 0), reverse=True)
        filtered_events = diversified[:MAX_RENDERED_GLOBE_EVENTS]
        hidden_count = total_filtered_count - len(filtered_events)
    else:
        filtered_events = all_filtered_events
    events_json_str = json.dumps(filtered_events)
    color_by_mode = "risk" if color_by.lower() == "risk" else "category"
    auto_rotate_js = "true" if auto_rotate else "false"
    selected_id_js = f'"{selected_event_id}"' if selected_event_id else "null"

    # Local-first texture set (bundled with holo-view-maker) — each falls
    # back to the existing live CDN URL below if the local file is missing.
    local_day_tex = _local_texture_data_uri("earth_atmos_2048.jpg", "image/jpeg")
    local_normal_tex = _local_texture_data_uri("earth_normal_2048.jpg", "image/jpeg")
    local_specular_tex = _local_texture_data_uri("earth_specular_2048.jpg", "image/jpeg")
    local_lights_tex = _local_texture_data_uri("earth_lights_2048.png", "image/png")
    local_clouds_tex = _local_texture_data_uri("earth_clouds_1024.png", "image/png")
    coastline_geojson = _local_coastline_geojson()

    local_day_tex_js = json.dumps(local_day_tex)
    local_normal_tex_js = json.dumps(local_normal_tex)
    local_specular_tex_js = json.dumps(local_specular_tex)
    local_lights_tex_js = json.dumps(local_lights_tex)
    local_clouds_tex_js = json.dumps(local_clouds_tex)
    coastline_geojson_js = coastline_geojson if coastline_geojson else "null"

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>3D Holo Globe</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600;700&display=swap');
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body, html {{ width: 100%; height: 100%; overflow: hidden; background: #04060a; font-family: 'IBM Plex Sans', sans-serif; color: #e8e9ea; }}
    #canvas-container {{ width: 100%; height: 100%; position: absolute; top: 0; left: 0; z-index: 1; }}
    
    /* Command Center HUD Overlays */
    .hud {{ position: absolute; z-index: 10; pointer-events: auto; }}
    .hud-header {{ top: 16px; left: 16px; display: flex; flex-direction: column; gap: 4px; pointer-events: none; }}
    .hud-title {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.78rem; font-weight: 600; letter-spacing: 0.12em; color: #4d8fc4; text-transform: uppercase; text-shadow: 0 0 10px rgba(77,143,196,0.6); display: flex; align-items: center; gap: 8px; }}
    .pulse-dot {{ width: 7px; height: 7px; border-radius: 50%; background: #0ca30c; box-shadow: 0 0 8px #0ca30c; animation: pulse 2s infinite; }}
    @keyframes pulse {{ 0%, 100% {{ opacity: 1; transform: scale(1); }} 50% {{ opacity: 0.4; transform: scale(0.85); }} }}
    .hud-subtitle {{ font-size: 0.72rem; color: #9a9da1; font-family: 'IBM Plex Mono', monospace; }}

    .hud-stats {{ top: 16px; right: 16px; display: flex; gap: 10px; }}
    .stat-pill {{ background: rgba(10, 14, 20, 0.88); backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 6px; padding: 6px 12px; text-align: right; box-shadow: 0 4px 14px rgba(0,0,0,0.6); }}
    .stat-pill .lbl {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.58rem; color: #7f8691; text-transform: uppercase; letter-spacing: 0.06em; }}
    .stat-pill .val {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.95rem; font-weight: 600; color: #e8e9ea; }}

    /* Real-time Altitude & Resolution Indicator */
    .hud-altitude {{
      top: 56px; left: 16px;
      font-family: 'IBM Plex Mono', monospace; font-size: 0.68rem; font-weight: 600;
      color: #38bdf8; background: rgba(4, 10, 20, 0.88); backdrop-filter: blur(8px);
      padding: 4px 10px; border-radius: 4px; border: 1px solid rgba(56, 189, 248, 0.3);
      display: flex; align-items: center; gap: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.5);
    }}
    .res-badge {{ font-size: 0.62rem; padding: 1px 6px; border-radius: 3px; background: rgba(12, 163, 12, 0.2); border: 1px solid #0ca30c; color: #4ade80; }}

    /* Quick Floating Controls */
    .hud-controls {{ top: 92px; left: 16px; display: flex; flex-direction: column; gap: 6px; }}
    .hud-btn {{ background: rgba(10, 15, 24, 0.88); backdrop-filter: blur(6px); border: 1px solid rgba(255, 255, 255, 0.14); color: #e8e9ea; font-family: 'IBM Plex Mono', monospace; font-size: 0.68rem; padding: 6px 11px; border-radius: 4px; cursor: pointer; display: flex; align-items: center; gap: 6px; transition: all 0.15s ease; }}
    .hud-btn:hover {{ background: rgba(56, 189, 248, 0.25); border-color: #38bdf8; color: #ffffff; transform: translateX(2px); }}
    .hud-btn.active {{ background: #38bdf8; color: #04060a; font-weight: 600; }}
    .hud-btn.highlight {{ border-color: #fab219; color: #fab219; }}
    .hud-btn.highlight:hover {{ background: rgba(250, 178, 25, 0.25); color: #ffffff; }}

    /* Bottom Prompt */
    .hud-prompt {{
      bottom: 20px; left: 50%; transform: translateX(-50%);
      pointer-events: none;
      font-family: 'IBM Plex Mono', monospace; font-size: 0.72rem; font-weight: 600;
      letter-spacing: 0.14em; text-transform: uppercase;
      color: #7dd3fc;
      text-shadow: 0 0 12px rgba(56, 189, 248, 0.8);
      background: rgba(4, 8, 15, 0.82); backdrop-filter: blur(8px);
      padding: 6px 18px; border-radius: 20px; border: 1px solid rgba(56, 189, 248, 0.35);
      white-space: nowrap;
    }}

    /* Detail Panel Card */
    #detail-card {{
      bottom: 16px; right: 16px; width: 320px; max-height: calc(100% - 90px);
      background: rgba(10, 15, 24, 0.94); backdrop-filter: blur(16px);
      border: 1px solid rgba(56, 189, 248, 0.35); border-radius: 8px;
      padding: 14px 16px; box-shadow: 0 8px 30px rgba(0,0,0,0.85), 0 0 24px rgba(56,189,248,0.2);
      display: none; flex-direction: column; gap: 10px; overflow-y: auto;
      transition: all 0.25s ease;
    }}
    #detail-card.active {{ display: flex; }}
    .card-top {{ display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 8px; }}
    .card-id {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.92rem; font-weight: 600; color: #e8e9ea; }}
    .card-close {{ cursor: pointer; color: #7f8691; font-size: 1.2rem; line-height: 1; border: none; background: transparent; padding: 0 4px; }}
    .card-close:hover {{ color: #e8e9ea; }}
    .card-region {{ font-size: 0.82rem; font-weight: 500; color: #e8e9ea; }}
    .card-badge {{ display: inline-block; font-family: 'IBM Plex Mono', monospace; font-size: 0.65rem; font-weight: 600; padding: 2px 7px; border-radius: 4px; text-transform: uppercase; margin-top: 4px; }}
    
    .risk-bar-wrap {{ margin: 4px 0; }}
    .risk-bar-label {{ display: flex; justify-content: space-between; font-family: 'IBM Plex Mono', monospace; font-size: 0.65rem; color: #9a9da1; margin-bottom: 3px; }}
    .risk-bar-track {{ height: 5px; background: rgba(255,255,255,0.1); border-radius: 3px; overflow: hidden; }}
    .risk-bar-fill {{ height: 100%; width: 0%; border-radius: 3px; transition: width 0.4s ease; }}

    .card-rows {{ display: flex; flex-direction: column; gap: 4px; font-size: 0.74rem; }}
    .card-row {{ display: flex; justify-content: space-between; border-bottom: 1px dashed rgba(255,255,255,0.06); padding: 3px 0; }}
    .card-row .k {{ color: #9a9da1; }}
    .card-row .v {{ font-family: 'IBM Plex Mono', monospace; color: #e8e9ea; }}

    .card-btn-row {{ display: flex; gap: 8px; margin-top: 6px; }}
    .card-action-btn {{ flex: 1; background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.4); color: #7dd3fc; padding: 6px; border-radius: 4px; font-family: 'IBM Plex Mono', monospace; font-size: 0.68rem; font-weight: 600; cursor: pointer; text-align: center; text-transform: uppercase; transition: all 0.15s ease; }}
    .card-action-btn:hover {{ background: #38bdf8; color: #04060a; }}
  </style>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
</head>
<body>
  <div id="canvas-container"></div>

  <!-- HUD Header -->
  <div class="hud hud-header">
    <div class="hud-title"><span class="pulse-dot"></span> SIH26162 · 3D ORBITAL THERMAL RADAR</div>
    <div class="hud-subtitle">Interactive Digital Twin &middot; High-Resolution 2D Satellite Inspection</div>
    {f'<div class="hud-subtitle" style="color:#fab219;">Showing top {len(filtered_events)} of {total_filtered_count} by risk score — raise Min Risk Score or narrow the region to see fewer, less-overlapping markers</div>' if hidden_count else ''}
  </div>

  <!-- HUD Altitude & Status -->
  <div class="hud hud-altitude" id="hud-altitude">
    <span id="alt-txt">ALTITUDE: ORBITAL (1,200 km)</span>
    <span class="res-badge" id="res-badge">GLOBAL SATELLITE</span>
  </div>

  <!-- HUD Stats -->
  <div class="hud hud-stats">
    <div class="stat-pill">
      <div class="lbl">{"Shown / Total" if hidden_count else "Total Active"}</div>
      <div class="val" id="stat-total">{f"{len(filtered_events)} / {total_filtered_count}" if hidden_count else len(filtered_events)}</div>
    </div>
    <div class="stat-pill">
      <div class="lbl">Critical Risk</div>
      <div class="val" style="color:#e66767;" id="stat-critical">{sum(1 for e in all_filtered_events if e.get("riskLevel") == "CRITICAL")}</div>
    </div>
    <div class="stat-pill">
      <div class="lbl">High Risk</div>
      <div class="val" style="color:#ec835a;" id="stat-high">{sum(1 for e in all_filtered_events if e.get("riskLevel") == "HIGH")}</div>
    </div>
    <div class="stat-pill">
      <div class="lbl">Total FRP</div>
      <div class="val" style="color:#fab219;" id="stat-frp">{sum(e.get("frp", 0) for e in all_filtered_events):.0f} MW</div>
    </div>
  </div>

  <!-- Quick Floating Controls -->
  <div class="hud hud-controls">
    <button class="hud-btn highlight" id="btn-belt-2d" onclick="focusBelt2D()">🎯 Zoom Belt (2D Map)</button>
    <button class="hud-btn" id="btn-india" onclick="focusIndia()">🇮🇳 Focus India</button>
    <button class="hud-btn" id="btn-top-risk" onclick="focusTopRisk()">🔥 Highest Risk Hotspot</button>
    <button class="hud-btn" id="btn-reset" onclick="resetToOrbit()">🌍 Orbital Overview</button>
    <button class="hud-btn" id="btn-spin" onclick="toggleSpin()">🔄 Auto-Spin: ON</button>
    <button class="hud-btn" id="btn-mode" onclick="toggleColorMode()">🎨 Mode: {color_by_mode.upper()}</button>
  </div>

  <!-- Bottom Monospace Prompt -->
  <div class="hud hud-prompt" id="hud-prompt">
    SCROLL TO DEEP ZOOM &middot; DOUBLE-CLICK ANYWHERE TO INSPECT 2D SATELLITE MAP &middot; CLICK BEAM
  </div>

  <!-- Selected Event Detail Card -->
  <div class="hud" id="detail-card">
    <div class="card-top">
      <div>
        <div class="card-id" id="card-id">TI-0001</div>
        <div class="card-region" id="card-region">Industrial Cluster</div>
      </div>
      <button class="card-close" onclick="closeCard()">&times;</button>
    </div>
    <div id="card-badge-container"></div>
    <div class="risk-bar-wrap">
      <div class="risk-bar-label">
        <span>RISK SCORE</span>
        <span id="card-risk-val" style="font-weight:600;">85/100</span>
      </div>
      <div class="risk-bar-track">
        <div class="risk-bar-fill" id="card-risk-fill"></div>
      </div>
    </div>
    <div class="card-rows">
      <div class="card-row"><span class="k">Coordinates</span><span class="v" id="card-coords">22.80, 86.18</span></div>
      <div class="card-row"><span class="k">Fire Radiative Power</span><span class="v" id="card-frp">18.5 MW</span></div>
      <div class="card-row"><span class="k">Brightness Temp</span><span class="v" id="card-brightness">345 K</span></div>
      <div class="card-row"><span class="k">AI Confidence</span><span class="v" id="card-conf">88%</span></div>
      <div class="card-row"><span class="k">Persistence</span><span class="v" id="card-persist">14 days</span></div>
      <div class="card-row"><span class="k">Satellite Sensor</span><span class="v" id="card-sat">VIIRS S-NPP</span></div>
      <div class="card-row"><span class="k">Status</span><span class="v" id="card-status">CRITICAL</span></div>
    </div>
    <div class="card-btn-row">
      <button class="card-action-btn" onclick="recenterSelected2D()">🔍 2D Aerial Zoom</button>
    </div>
  </div>

  <script>
    // --- Configuration & Constants ---
    const RAW_EVENTS = {events_json_str};
    const COASTLINE_GEOJSON = {coastline_geojson_js};
    let colorByMode = "{color_by_mode}";
    let isSpinning = {auto_rotate_js};
    let initialSelectedId = {selected_id_js};

    const CATEGORY_COLORS = {{
      "Likely Industrial Fire": "#3987e5",
      "Persistent Non-Industrial Thermal Source": "#d95926",
      "Transient Industrial Flare": "#199e70",
      "Likely Agricultural Burning": "#c98500",
      "Sun Glint / False Positive": "#d55181",
      "Likely Wildfire": "#008300",
      "Persistent Industrial Activity": "#9085e9",
      "Requires Verification": "#e66767"
    }};

    const RISK_COLORS = {{
      "CRITICAL": "#e66767",
      "HIGH": "#ec835a",
      "MODERATE": "#fab219",
      "LOW": "#0ca30c"
    }};

    const GLOBE_RADIUS = 2.0;

    // --- Three.js Setup ---
    const container = document.getElementById("canvas-container");
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x030508);

    const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.01, 1000);
    camera.position.set(0, 1.4, 4.8);

    const renderer = new THREE.WebGLRenderer({{ antialias: true, alpha: false, powerPreference: "high-performance" }});
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2.5));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.15;
    container.appendChild(renderer.domElement);

    const controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    // DEEP ZOOM: Allow getting right down to ground level (0.012 above surface)
    controls.minDistance = 2.012;
    controls.maxDistance = 14.0;
    controls.zoomSpeed = 1.1;
    controls.autoRotate = isSpinning;
    controls.autoRotateSpeed = 0.5;

    // Stop auto-rotation whenever the user interacts with the camera
    controls.addEventListener('start', () => {{
      if (isSpinning) {{
        isSpinning = false;
        controls.autoRotate = false;
        const btn = document.getElementById("btn-spin");
        if (btn) btn.innerText = "🔄 Auto-Spin: OFF";
      }}
    }});

    // --- Starfield Background ---
    const starsGeo = new THREE.BufferGeometry();
    const starCount = 1800;
    const starPositions = new Float32Array(starCount * 3);
    for(let i=0; i<starCount*3; i+=3) {{
      const r = 50 + Math.random() * 80;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos((Math.random() * 2) - 1);
      starPositions[i] = r * Math.sin(phi) * Math.cos(theta);
      starPositions[i+1] = r * Math.cos(phi);
      starPositions[i+2] = r * Math.sin(phi) * Math.sin(theta);
    }}
    starsGeo.setAttribute('position', new THREE.BufferAttribute(starPositions, 3));
    const starsMat = new THREE.PointsMaterial({{ color: 0x8bb2d6, size: 0.85, transparent: true, opacity: 0.75 }});
    const starField = new THREE.Points(starsGeo, starsMat);
    scene.add(starField);

    // --- Lighting ---
    const ambientLight = new THREE.AmbientLight(0xdde8f5, 0.55);
    scene.add(ambientLight);

    const sunLight = new THREE.DirectionalLight(0xfff7ed, 2.6);
    sunLight.position.set(6, 2.8, 4.5);
    scene.add(sunLight);

    const nightRimLight = new THREE.DirectionalLight(0x38bdf8, 0.4);
    nightRimLight.position.set(-6, -2, -4);
    scene.add(nightRimLight);

    // --- Earth Group ---
    const earthGroup = new THREE.Group();
    // Rotate to bring India and South Asia to front-and-center
    earthGroup.rotation.y = ((80 + 180) * Math.PI) / 180 - Math.PI / 2;
    scene.add(earthGroup);

    const texLoader = new THREE.TextureLoader();
    texLoader.crossOrigin = "anonymous";

    // 1. Earth Base Mesh (NASA Blue Marble Globe)
    const earthGeo = new THREE.SphereGeometry(GLOBE_RADIUS, 128, 128);
    
    function createProceduralEarthCanvas() {{
      // Soft placeholder gradient shown only until the real Blue Marble
      // texture finishes loading (or if the CDN is unreachable) — no fake
      // landmass shapes, just a neutral ocean tone so it never misleads.
      const canvas = document.createElement('canvas');
      canvas.width = 1024;
      canvas.height = 512;
      const ctx = canvas.getContext('2d');
      const oceanGrad = ctx.createLinearGradient(0, 0, 0, canvas.height);
      oceanGrad.addColorStop(0, '#123a5e');
      oceanGrad.addColorStop(0.5, '#0d325c');
      oceanGrad.addColorStop(1, '#081c36');
      ctx.fillStyle = oceanGrad;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      return new THREE.CanvasTexture(canvas);
    }}

    const defaultDayTex = createProceduralEarthCanvas();
    const earthMat = new THREE.MeshPhongMaterial({{
      map: defaultDayTex,
      specular: new THREE.Color(0x1b4a68),
      shininess: 22
    }});
    const earthMesh = new THREE.Mesh(earthGeo, earthMat);
    earthGroup.add(earthMesh);

    // Local-first texture set bundled with the app (instant, zero network
    // dependency) — falls back to the live CDN copy only if the local file
    // wasn't available when the page was generated.
    const LOCAL_DAY_TEX = {local_day_tex_js};
    const LOCAL_NORMAL_TEX = {local_normal_tex_js};
    const LOCAL_SPECULAR_TEX = {local_specular_tex_js};

    texLoader.load(
      LOCAL_DAY_TEX || "https://unpkg.com/three-globe/example/img/earth-blue-marble.jpg",
      (tex) => {{
        tex.colorSpace = THREE.SRGBColorSpace;
        tex.anisotropy = 16;
        tex.generateMipmaps = true;
        earthMat.map = tex;
        earthMat.needsUpdate = true;
      }}
    );

    // Real terrain relief — mountain ranges, ridges, and coastal shelves
    // catch the sun light instead of the whole globe looking like a flat
    // painted ball. Prefer a proper normal map (local asset); fall back to
    // a plain bump map from the CDN copy if the local texture is missing.
    if (LOCAL_NORMAL_TEX) {{
      texLoader.load(LOCAL_NORMAL_TEX, (tex) => {{
        earthMat.normalMap = tex;
        earthMat.normalScale = new THREE.Vector2(0.85, 0.85);
        earthMat.needsUpdate = true;
      }});
    }} else {{
      texLoader.load(
        "https://unpkg.com/three-globe/example/img/earth-topology.png",
        (tex) => {{
          earthMat.bumpMap = tex;
          earthMat.bumpScale = 0.045;
          earthMat.needsUpdate = true;
        }}
      );
    }}

    // Ocean specular mask — makes seas glint under the sun while land
    // stays matte, instead of one uniform specular value everywhere.
    texLoader.load(
      LOCAL_SPECULAR_TEX || "https://unpkg.com/three-globe/example/img/earth-water.png",
      (tex) => {{
        earthMat.specularMap = tex;
        earthMat.needsUpdate = true;
      }}
    );

    // 2. DEDICATED REGIONAL HIGH-RESOLUTION SATELLITE CURVED PATCH
    // Covers the entire Jharkhand–Odisha Iron Ore & Steel Mining Belt (Lat 20.0 to 25.5 N, Lon 83.0 to 88.5 E)
    // Uses a dedicated 2048x2048 canvas with Level 9/10/11 Esri Satellite Tiles for razor-sharp ground details
    const REG_MIN_LAT = 19.8, REG_MAX_LAT = 25.8;
    const REG_MIN_LON = 83.0, REG_MAX_LON = 89.0;
    const regPhiStart = (90 - REG_MAX_LAT) * (Math.PI / 180);
    const regPhiLength = (REG_MAX_LAT - REG_MIN_LAT) * (Math.PI / 180);
    const regThetaStart = (REG_MIN_LON + 180) * (Math.PI / 180);
    const regThetaLength = (REG_MAX_LON - REG_MIN_LON) * (Math.PI / 180);

    const regionalPatchGeo = new THREE.SphereGeometry(
      GLOBE_RADIUS * 1.0008, 96, 96,
      regThetaStart, regThetaLength, regPhiStart, regPhiLength
    );

    const regionalCanvas = document.createElement('canvas');
    regionalCanvas.width = 2048;
    regionalCanvas.height = 2048;
    const regionalCtx = regionalCanvas.getContext('2d');

    // Fill initial high-contrast natural terrain palette
    regionalCtx.fillStyle = '#223826';
    regionalCtx.fillRect(0, 0, regionalCanvas.width, regionalCanvas.height);

    const regionalSatTexture = new THREE.CanvasTexture(regionalCanvas);
    regionalSatTexture.colorSpace = THREE.SRGBColorSpace;
    regionalSatTexture.anisotropy = 16;
    regionalSatTexture.generateMipmaps = true;
    regionalSatTexture.minFilter = THREE.LinearMipmapLinearFilter;
    regionalSatTexture.magFilter = THREE.LinearFilter;

    const regionalPatchMat = new THREE.MeshBasicMaterial({{
      map: regionalSatTexture,
      transparent: true,
      opacity: 0.0,
      depthWrite: false,
      polygonOffset: true,
      polygonOffsetFactor: -1,
      polygonOffsetUnits: -1
    }});
    const regionalPatchMesh = new THREE.Mesh(regionalPatchGeo, regionalPatchMat);
    earthGroup.add(regionalPatchMesh);

    // Shared tile loader with one retry, then a neutral-tint fallback —
    // a flaky/blocked tile server previously left a permanent blank gap
    // with no retry and no visual indication anything had failed.
    function loadTileImage(url, onload, onfail, retriesLeft) {{
      if (retriesLeft === undefined) retriesLeft = 1;
      const img = new Image();
      img.crossOrigin = "anonymous";
      img.onload = () => onload(img);
      img.onerror = () => {{
        if (retriesLeft > 0) {{
          setTimeout(() => loadTileImage(url, onload, onfail, retriesLeft - 1), 500);
        }} else {{
          onfail();
        }}
      }};
      img.src = url;
    }}

    // Dynamic Esri Satellite Tile Stitcher for Regional Curved Patch
    function loadRegionalHighResSatelliteTiles() {{
      const z = 8; // Zoom level 8 provides high-detail ~600m resolution per tile
      const n = Math.pow(2, z);

      function lonToX(lon) {{ return ((lon + 180) / 360) * n; }}
      function latToY(lat) {{
        const latRad = lat * Math.PI / 180;
        return ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n;
      }}

      const startX = Math.floor(lonToX(REG_MIN_LON));
      const endX = Math.floor(lonToX(REG_MAX_LON));
      const startY = Math.floor(latToY(REG_MAX_LAT));
      const endY = Math.floor(latToY(REG_MIN_LAT));

      for (let x = startX; x <= endX; x++) {{
        for (let y = startY; y <= endY; y++) {{
          const curX = x, curY = y;
          const tileUrl = `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${{z}}/${{curY}}/${{curX}}`;

          const tileLonLeft = (curX / n) * 360 - 180;
          const tileLonRight = ((curX + 1) / n) * 360 - 180;
          const tileLatTop = Math.atan(Math.sinh(Math.PI * (1 - (2 * curY) / n))) * 180 / Math.PI;
          const tileLatBottom = Math.atan(Math.sinh(Math.PI * (1 - (2 * (curY + 1)) / n))) * 180 / Math.PI;

          // Map into the regional patch 2048x2048 canvas
          const dx = ((tileLonLeft - REG_MIN_LON) / (REG_MAX_LON - REG_MIN_LON)) * regionalCanvas.width;
          const dw = ((tileLonRight - tileLonLeft) / (REG_MAX_LON - REG_MIN_LON)) * regionalCanvas.width;
          const dy = ((REG_MAX_LAT - tileLatTop) / (REG_MAX_LAT - REG_MIN_LAT)) * regionalCanvas.height;
          const dh = ((tileLatTop - tileLatBottom) / (REG_MAX_LAT - REG_MIN_LAT)) * regionalCanvas.height;

          loadTileImage(
            tileUrl,
            (img) => {{
              regionalCtx.drawImage(img, dx, dy, dw + 1, dh + 1);
              regionalSatTexture.needsUpdate = true;
            }},
            () => {{
              regionalCtx.fillStyle = "#223826";
              regionalCtx.fillRect(dx, dy, dw + 1, dh + 1);
              regionalSatTexture.needsUpdate = true;
            }}
          );
        }}
      }}
    }}
    loadRegionalHighResSatelliteTiles();

    // 3. Dynamic Local Patch for any Focused Hotspot / Coordinate
    let localPatchMesh = null;
    const localCanvas = document.createElement('canvas');
    localCanvas.width = 1024;
    localCanvas.height = 1024;
    const localCtx = localCanvas.getContext('2d');
    const localTexture = new THREE.CanvasTexture(localCanvas);
    localTexture.colorSpace = THREE.SRGBColorSpace;
    localTexture.anisotropy = 16;
    localTexture.generateMipmaps = true;

    const localMat = new THREE.MeshBasicMaterial({{
      map: localTexture,
      transparent: true,
      opacity: 0.0,
      depthWrite: false,
      polygonOffset: true,
      polygonOffsetFactor: -2,
      polygonOffsetUnits: -2
    }});

    function updateLocalSatellitePatch(centerLat, centerLon) {{
      const span = 2.4;
      const minLat = centerLat - span, maxLat = centerLat + span;
      const minLon = centerLon - span, maxLon = centerLon + span;

      if (localPatchMesh) {{
        earthGroup.remove(localPatchMesh);
        localPatchMesh.geometry.dispose();
      }}

      const phiStart = (90 - maxLat) * (Math.PI / 180);
      const phiLength = (maxLat - minLat) * (Math.PI / 180);
      const thetaStart = (minLon + 180) * (Math.PI / 180);
      const thetaLength = (maxLon - minLon) * (Math.PI / 180);

      const localGeo = new THREE.SphereGeometry(
        GLOBE_RADIUS * 1.0012, 64, 64,
        thetaStart, thetaLength, phiStart, phiLength
      );
      localPatchMesh = new THREE.Mesh(localGeo, localMat);
      earthGroup.add(localPatchMesh);

      // Load zoom 10 high-resolution satellite tiles (~150m detail per pixel)
      localCtx.fillStyle = '#223826';
      localCtx.fillRect(0, 0, localCanvas.width, localCanvas.height);
      localTexture.needsUpdate = true;

      const z = 10;
      const n = Math.pow(2, z);
      function lonToX(lon) {{ return ((lon + 180) / 360) * n; }}
      function latToY(lat) {{
        const latRad = lat * Math.PI / 180;
        return ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * n;
      }}

      const startX = Math.floor(lonToX(minLon));
      const endX = Math.floor(lonToX(maxLon));
      const startY = Math.floor(latToY(maxLat));
      const endY = Math.floor(latToY(minLat));

      for (let x = startX; x <= endX; x++) {{
        for (let y = startY; y <= endY; y++) {{
          const curX = x, curY = y;
          const tileUrl = `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/${{z}}/${{curY}}/${{curX}}`;

          const tileLonLeft = (curX / n) * 360 - 180;
          const tileLonRight = ((curX + 1) / n) * 360 - 180;
          const tileLatTop = Math.atan(Math.sinh(Math.PI * (1 - (2 * curY) / n))) * 180 / Math.PI;
          const tileLatBottom = Math.atan(Math.sinh(Math.PI * (1 - (2 * (curY + 1)) / n))) * 180 / Math.PI;

          const dx = ((tileLonLeft - minLon) / (maxLon - minLon)) * localCanvas.width;
          const dw = ((tileLonRight - tileLonLeft) / (maxLon - minLon)) * localCanvas.width;
          const dy = ((maxLat - tileLatTop) / (maxLat - minLat)) * localCanvas.height;
          const dh = ((tileLatTop - tileLatBottom) / (maxLat - minLat)) * localCanvas.height;

          loadTileImage(
            tileUrl,
            (img) => {{
              localCtx.drawImage(img, dx, dy, dw + 1, dh + 1);
              localTexture.needsUpdate = true;
            }},
            () => {{
              localCtx.fillStyle = "#223826";
              localCtx.fillRect(dx, dy, dw + 1, dh + 1);
              localTexture.needsUpdate = true;
            }}
          );
        }}
      }}
    }}

    // 4. City lights on the dark side
    const LOCAL_LIGHTS_TEX = {local_lights_tex_js};
    let lightsMesh = null;
    texLoader.load(
      LOCAL_LIGHTS_TEX || "https://unpkg.com/three-globe/example/img/earth-night.jpg",
      (lightsTex) => {{
        lightsTex.colorSpace = THREE.SRGBColorSpace;
        const lightsMat = new THREE.MeshBasicMaterial({{
          map: lightsTex,
          blending: THREE.AdditiveBlending,
          transparent: true,
          opacity: 0.55,
          depthWrite: false
        }});
        lightsMesh = new THREE.Mesh(new THREE.SphereGeometry(GLOBE_RADIUS * 1.001, 96, 96), lightsMat);
        earthGroup.add(lightsMesh);
      }}
    );

    // 5. Drifting cloud shell
    const LOCAL_CLOUDS_TEX = {local_clouds_tex_js};
    let cloudsMesh = null;
    texLoader.load(
      LOCAL_CLOUDS_TEX || "https://unpkg.com/three-globe/example/img/clouds.png",
      (cloudsTex) => {{
        const cloudsMat = new THREE.MeshLambertMaterial({{
          map: cloudsTex,
          transparent: true,
          opacity: 0.42,
          blending: THREE.AdditiveBlending,
          depthWrite: false
        }});
        cloudsMesh = new THREE.Mesh(new THREE.SphereGeometry(GLOBE_RADIUS * 1.012, 64, 64), cloudsMat);
        earthGroup.add(cloudsMesh);
      }}
    );

    // 6. Vibrant Cyan Atmospheric Glow Halo (Dissolves on Deep Zoom)
    const atmosVertexShader = `
      varying vec3 vNormal;
      varying vec3 vPosition;
      void main() {{
        vNormal = normalize(normalMatrix * normal);
        vPosition = (modelViewMatrix * vec4(position, 1.0)).xyz;
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }}
    `;

    const atmosFragmentShader = `
      varying vec3 vNormal;
      varying vec3 vPosition;
      uniform float uOpacity;
      void main() {{
        vec3 viewDir = normalize(-vPosition);
        float intensity = pow(0.68 - dot(vNormal, viewDir), 2.2);
        vec3 atmosColor = vec3(0.22, 0.74, 0.98);
        gl_FragColor = vec4(atmosColor, intensity * 1.6 * uOpacity);
      }}
    `;

    const atmosMaterial = new THREE.ShaderMaterial({{
      vertexShader: atmosVertexShader,
      fragmentShader: atmosFragmentShader,
      uniforms: {{ uOpacity: {{ value: 1.0 }} }},
      blending: THREE.AdditiveBlending,
      side: THREE.BackSide,
      transparent: true,
      depthWrite: false
    }});

    const atmosphereMesh = new THREE.Mesh(new THREE.SphereGeometry(GLOBE_RADIUS * 1.15, 64, 64), atmosMaterial);
    scene.add(atmosphereMesh);

    const innerAtmosMat = new THREE.ShaderMaterial({{
      vertexShader: atmosVertexShader,
      fragmentShader: `
        varying vec3 vNormal;
        varying vec3 vPosition;
        uniform float uOpacity;
        void main() {{
          vec3 viewDir = normalize(-vPosition);
          float intensity = pow(1.0 - dot(vNormal, viewDir), 3.2);
          gl_FragColor = vec4(0.24, 0.72, 0.98, intensity * 0.45 * uOpacity);
        }}
      `,
      uniforms: {{ uOpacity: {{ value: 1.0 }} }},
      blending: THREE.AdditiveBlending,
      side: THREE.FrontSide,
      transparent: true,
      depthWrite: false
    }});
    const innerAtmosMesh = new THREE.Mesh(new THREE.SphereGeometry(GLOBE_RADIUS * 1.003, 64, 64), innerAtmosMat);
    earthGroup.add(innerAtmosMesh);

    // Coordinate Graticule (Lat/Lon Lines)
    const gridMat = new THREE.LineBasicMaterial({{ color: 0x38bdf8, transparent: true, opacity: 0.18 }});
    for (let lat = -75; lat <= 75; lat += 15) {{
      const phi = (90 - lat) * (Math.PI / 180);
      const r = GLOBE_RADIUS * 1.002 * Math.sin(phi);
      const y = GLOBE_RADIUS * 1.002 * Math.cos(phi);
      const pts = [];
      for (let theta = 0; theta <= Math.PI * 2; theta += Math.PI / 36) {{
        pts.push(new THREE.Vector3(r * Math.cos(theta), y, r * Math.sin(theta)));
      }}
      earthGroup.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), gridMat));
    }}

    // Helper Coordinate Math
    function latLonToVec3(lat, lon, radius) {{
      const phi = (90 - lat) * (Math.PI / 180);
      const theta = (lon + 180) * (Math.PI / 180);
      return new THREE.Vector3(
        -radius * Math.sin(phi) * Math.cos(theta),
        radius * Math.cos(phi),
        radius * Math.sin(phi) * Math.sin(theta)
      );
    }}

    function vec3ToLatLon(vec, radius) {{
      const norm = vec.clone().normalize();
      const phi = Math.acos(norm.y);
      const lat = 90 - (phi * 180) / Math.PI;
      const theta = Math.atan2(norm.z, -norm.x);
      let lon = (theta * 180) / Math.PI - 180;
      if (lon < -180) lon += 360;
      return {{ lat, lon }};
    }}

    // Real coastline outlines (Natural Earth 110m land polygons, bundled
    // locally) — the globe previously relied purely on the photo texture
    // for landmass shape, with no actual geographic line data.
    function buildCoastlines() {{
      if (!COASTLINE_GEOJSON) return;
      const coastMat = new THREE.LineBasicMaterial({{ color: 0x8fa8c2, transparent: true, opacity: 0.4 }});
      const coastRadius = GLOBE_RADIUS * 1.002;

      function addRing(ring) {{
        const pts = ring.map(([lon, lat]) => latLonToVec3(lat, lon, coastRadius));
        const geo = new THREE.BufferGeometry().setFromPoints(pts);
        earthGroup.add(new THREE.LineLoop(geo, coastMat));
      }}

      COASTLINE_GEOJSON.features.forEach((feature) => {{
        const geom = feature && feature.geometry;
        if (!geom) return;
        if (geom.type === "Polygon") {{
          geom.coordinates.forEach(addRing);
        }} else if (geom.type === "MultiPolygon") {{
          geom.coordinates.forEach((rings) => rings.forEach(addRing));
        }}
      }});
    }}
    buildCoastlines();

    // --- Thermal Beams & Ground Markers ---
    const markersGroup = new THREE.Group();
    earthGroup.add(markersGroup);

    const interactiveObjects = [];
    const haloMeshes = [];
    const beamMeshes = [];
    let selectedMesh = null;
    let selectedEvent = null;

    function getEventColor(event) {{
      if (colorByMode === "risk") {{
        return RISK_COLORS[event.riskLevel] || "#fab219";
      }}
      return CATEGORY_COLORS[event.category] || "#e66767";
    }}

    function buildBeams() {{
      while(markersGroup.children.length > 0) {{
        markersGroup.remove(markersGroup.children[0]);
      }}
      interactiveObjects.length = 0;
      haloMeshes.length = 0;
      beamMeshes.length = 0;

      // With hundreds of markers genuinely spread across a wide geographic
      // area (not clustered in one small region), tall beams fan out into
      // a chaotic "hedgehog" silhouette from almost any camera angle —
      // each one individually correct (radially outward from its own
      // point), but visually unreadable en masse. Scale beam height down
      // as the rendered count grows so a wide spread reads as clean
      // scattered points instead.
      const densityFactor = Math.max(0.25, Math.min(1.0, 60 / RAW_EVENTS.length));

      RAW_EVENTS.forEach(event => {{
        const pos = latLonToVec3(event.latitude, event.longitude, GLOBE_RADIUS);
        const normal = pos.clone().normalize();
        const quat = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), normal);

        const baseHeight = (0.015 + (event.riskScore / 100) * 0.045) * densityFactor;
        const colorHex = getEventColor(event);
        const color = new THREE.Color(colorHex);

        const beamGroup = new THREE.Group();
        beamGroup.position.copy(pos);
        beamGroup.quaternion.copy(quat);
        beamGroup.userData = {{ event, baseHeight }};

        // 1. Vertical Glowing Cylinder Beam
        const cylGeo = new THREE.CylinderGeometry(0.004, 0.008, baseHeight, 12);
        const cylMat = new THREE.MeshBasicMaterial({{
          color: color,
          transparent: true,
          opacity: 0.88
        }});
        const cylinder = new THREE.Mesh(cylGeo, cylMat);
        cylinder.position.set(0, baseHeight / 2, 0);
        beamGroup.add(cylinder);

        // 2. Glowing Head Beacon
        const sphereGeo = new THREE.SphereGeometry(0.012, 16, 16);
        const sphereMat = new THREE.MeshBasicMaterial({{ color: color }});
        const beacon = new THREE.Mesh(sphereGeo, sphereMat);
        beacon.position.set(0, baseHeight, 0);
        beamGroup.add(beacon);

        // 3. Ground Halo Ring (Pulsates in 2D Satellite View)
        // Sized small enough that even a dense cluster of nearby grid-cell
        // events reads as distinct dots instead of merging into one blob.
        const ringGeo = new THREE.RingGeometry(0.016, 0.034, 24);
        const ringMat = new THREE.MeshBasicMaterial({{
          color: color,
          transparent: true,
          opacity: 0.65,
          side: THREE.DoubleSide
        }});
        const ring = new THREE.Mesh(ringGeo, ringMat);
        ring.rotation.x = -Math.PI / 2;
        ring.position.set(0, 0.004, 0);
        beamGroup.add(ring);

        // 4. Inner Tactical Hotspot Core Dot
        const coreGeo = new THREE.CircleGeometry(0.009, 16);
        const coreMat = new THREE.MeshBasicMaterial({{ color: color, side: THREE.DoubleSide }});
        const core = new THREE.Mesh(coreGeo, coreMat);
        core.rotation.x = -Math.PI / 2;
        core.position.set(0, 0.005, 0);
        beamGroup.add(core);

        markersGroup.add(beamGroup);
        interactiveObjects.push(cylinder, beacon, ring, core);
        haloMeshes.push({{ ring, core, event, baseScale: 1.0 }});
        beamMeshes.push({{ beamGroup, cylinder, beacon, baseHeight }});

        if (initialSelectedId && event.id === initialSelectedId) {{
          selectEvent(event, beamGroup);
        }}
      }});
    }}

    // --- Raycasting & Interaction ---
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();

    function onPointerMove(e) {{
      mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
      mouse.y = -(e.clientY / window.innerHeight) * 2 + 1;
      raycaster.setFromCamera(mouse, camera);
      const intersects = raycaster.intersectObjects(interactiveObjects, false);
      document.body.style.cursor = intersects.length > 0 ? "pointer" : "auto";
    }}

    // STOP AUTO ROTATION IMMEDIATELY ON BEAM CLICK
    function onClick(e) {{
      mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
      mouse.y = -(e.clientY / window.innerHeight) * 2 + 1;
      raycaster.setFromCamera(mouse, camera);
      const intersects = raycaster.intersectObjects(interactiveObjects, false);
      if (intersects.length > 0) {{
        // Stop spinning permanently upon click
        isSpinning = false;
        controls.autoRotate = false;
        const btnSpin = document.getElementById("btn-spin");
        if (btnSpin) btnSpin.innerText = "🔄 Auto-Spin: OFF";

        const hit = intersects[0].object;
        const beamGroup = hit.parent;
        if (beamGroup && beamGroup.userData && beamGroup.userData.event) {{
          selectEvent(beamGroup.userData.event, beamGroup);
        }}
      }}
    }}

    function onDoubleClick(e) {{
      mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
      mouse.y = -(e.clientY / window.innerHeight) * 2 + 1;
      raycaster.setFromCamera(mouse, camera);
      const earthHit = raycaster.intersectObject(earthMesh, false);
      if (earthHit.length > 0) {{
        isSpinning = false;
        controls.autoRotate = false;
        const btnSpin = document.getElementById("btn-spin");
        if (btnSpin) btnSpin.innerText = "🔄 Auto-Spin: OFF";

        const localPt = earthGroup.worldToLocal(earthHit[0].point.clone());
        const coords = vec3ToLatLon(localPt, GLOBE_RADIUS);
        updateLocalSatellitePatch(coords.lat, coords.lon);
        flyToLatLon(coords.lat, coords.lon, 2.10);
      }}
    }}

    function selectEvent(event, groupMesh) {{
      // Stop spinning on event selection
      isSpinning = false;
      controls.autoRotate = false;
      const btnSpin = document.getElementById("btn-spin");
      if (btnSpin) btnSpin.innerText = "🔄 Auto-Spin: OFF";

      selectedEvent = event;
      selectedMesh = groupMesh;
      
      const card = document.getElementById("detail-card");
      card.classList.add("active");
      document.getElementById("card-id").innerText = event.id;
      document.getElementById("card-region").innerText = event.region;
      
      const col = getEventColor(event);
      const badgeCont = document.getElementById("card-badge-container");
      badgeCont.innerHTML = `<span class="card-badge" style="background:${{col}}22;color:${{col}};border:1px solid ${{col}}66;">${{event.category}}</span>`;
      
      document.getElementById("card-risk-val").innerText = `${{event.riskScore}}/100 (${{event.riskLevel}})`;
      document.getElementById("card-risk-val").style.color = RISK_COLORS[event.riskLevel] || "#fab219";
      
      const fill = document.getElementById("card-risk-fill");
      fill.style.width = `${{event.riskScore}}%`;
      fill.style.background = RISK_COLORS[event.riskLevel] || "#fab219";
      
      document.getElementById("card-coords").innerText = `${{event.latitude.toFixed(4)}}, ${{event.longitude.toFixed(4)}}`;
      document.getElementById("card-frp").innerText = `${{event.frp.toFixed(1)}} MW`;
      document.getElementById("card-brightness").innerText = `${{event.brightness}} K`;
      document.getElementById("card-conf").innerText = `${{event.confidence}}%`;
      document.getElementById("card-persist").innerText = `${{event.persistenceDays}} days (${{event.detectionCount}} det)`;
      document.getElementById("card-sat").innerText = event.satellite;
      document.getElementById("card-status").innerText = event.status;

      if (event.latitude && event.longitude) {{
        updateLocalSatellitePatch(event.latitude, event.longitude);
        flyToLatLon(event.latitude, event.longitude, 2.10);
      }}
    }}

    function closeCard() {{
      document.getElementById("detail-card").classList.remove("active");
      selectedEvent = null;
      selectedMesh = null;
    }}

    function recenterSelected2D() {{
      if (selectedEvent && selectedEvent.latitude && selectedEvent.longitude) {{
        updateLocalSatellitePatch(selectedEvent.latitude, selectedEvent.longitude);
        flyToLatLon(selectedEvent.latitude, selectedEvent.longitude, 2.06);
      }}
    }}

    // --- Smooth Camera Fly-To Animation ---
    let isAnimatingFlight = false;
    function flyToLatLon(lat, lon, targetRadius = 2.10) {{
      isSpinning = false;
      controls.autoRotate = false;
      const btnSpin = document.getElementById("btn-spin");
      if (btnSpin) btnSpin.innerText = "🔄 Auto-Spin: OFF";

      const localPos = latLonToVec3(lat, lon, targetRadius);
      const worldTargetPos = earthGroup.localToWorld(localPos.clone());
      const startPos = camera.position.clone();
      const startTarget = controls.target.clone();
      const endTarget = new THREE.Vector3(0, 0, 0);

      isAnimatingFlight = true;
      let progress = 0;

      function step() {{
        progress += 0.04;
        const ease = 0.5 - 0.5 * Math.cos(Math.min(progress, 1) * Math.PI);
        camera.position.lerpVectors(startPos, worldTargetPos, ease);
        controls.target.lerpVectors(startTarget, endTarget, ease);
        controls.update();

        if (progress < 1) {{
          requestAnimationFrame(step);
        }} else {{
          isAnimatingFlight = false;
        }}
      }}
      step();
    }}

    // --- Preset Navigation Actions ---
    function focusBelt2D() {{
      flyToLatLon(22.80, 86.18, 2.09);
    }}

    function focusIndia() {{
      flyToLatLon(21.5, 80.0, 3.6);
    }}

    function focusTopRisk() {{
      if (RAW_EVENTS.length > 0) {{
        const topEvent = RAW_EVENTS[0];
        const matchBeam = markersGroup.children.find(c => c.userData && c.userData.event && c.userData.event.id === topEvent.id);
        selectEvent(topEvent, matchBeam || markersGroup.children[0]);
      }} else {{
        focusBelt2D();
      }}
    }}

    function resetToOrbit() {{
      isSpinning = true;
      controls.autoRotate = true;
      const btnSpin = document.getElementById("btn-spin");
      if (btnSpin) btnSpin.innerText = "🔄 Auto-Spin: ON";
      const startPos = camera.position.clone();
      const targetPos = new THREE.Vector3(0, 1.4, 4.8);
      let progress = 0;
      function anim() {{
        progress += 0.04;
        const ease = 0.5 - 0.5 * Math.cos(Math.min(progress, 1) * Math.PI);
        camera.position.lerpVectors(startPos, targetPos, ease);
        controls.target.set(0, 0, 0);
        controls.update();
        if (progress < 1) requestAnimationFrame(anim);
      }}
      anim();
    }}

    function toggleSpin() {{
      isSpinning = !isSpinning;
      controls.autoRotate = isSpinning;
      const btnSpin = document.getElementById("btn-spin");
      if (btnSpin) btnSpin.innerText = `🔄 Auto-Spin: ${{isSpinning ? "ON" : "OFF"}}`;
    }}

    function toggleColorMode() {{
      colorByMode = colorByMode === "category" ? "risk" : "category";
      document.getElementById("btn-mode").innerText = `🎨 Mode: ${{colorByMode.toUpperCase()}}`;
      buildBeams();
      if (selectedEvent) selectEvent(selectedEvent, selectedMesh);
    }}

    // --- Animation & Deep Zoom Render Loop ---
    const clock = new THREE.Clock();
    const altTxt = document.getElementById("alt-txt");
    const resBadge = document.getElementById("res-badge");

    function animate() {{
      requestAnimationFrame(animate);
      const delta = clock.getDelta();
      const elapsed = clock.getElapsedTime();

      const camDist = camera.position.length();
      const altKm = Math.round(Math.max(1, (camDist - GLOBE_RADIUS) / GLOBE_RADIUS * 6371));

      // altFactor: 1.0 in outer orbit (>= 3.2), 0.0 at surface (<= 2.12)
      const altFactor = Math.max(0, Math.min(1, (camDist - 2.12) / (3.2 - 2.12)));

      // 1. Drifting Clouds Fade Out Completely on Zoom
      if (cloudsMesh) {{
        cloudsMesh.rotation.y += delta * 0.015;
        cloudsMesh.material.opacity = 0.42 * Math.pow(altFactor, 2.0);
      }}

      // 2. Atmospheric Cyan Halo Dissolves on Deep Zoom for 100% clear ground view
      if (atmosphereMesh && atmosphereMesh.material.uniforms) {{
        atmosphereMesh.material.uniforms.uOpacity.value = Math.pow(altFactor, 1.6);
      }}
      if (innerAtmosMesh && innerAtmosMesh.material.uniforms) {{
        innerAtmosMesh.material.uniforms.uOpacity.value = Math.pow(altFactor, 1.2);
      }}

      // 3. High-Resolution Regional & Local Satellite Patches Blend to 100% Clarity
      const satBlend = Math.max(0, Math.min(1, (2.85 - camDist) / (2.85 - 2.10)));
      if (regionalPatchMat) {{
        regionalPatchMat.opacity = THREE.MathUtils.lerp(0.0, 1.0, satBlend);
      }}
      if (localMat) {{
        localMat.opacity = THREE.MathUtils.lerp(0.0, 1.0, satBlend);
      }}

      // 4. Adaptive Beam Height on Close Zoom
      const beamScaleFactor = Math.max(0.15, Math.min(1.0, (camDist - 2.04) / 0.8));
      beamMeshes.forEach(b => {{
        const h = b.baseHeight * beamScaleFactor;
        b.cylinder.scale.set(1, beamScaleFactor, 1);
        b.cylinder.position.set(0, h / 2, 0);
        b.beacon.position.set(0, h, 0);
      }});

      // 5. Pulsating Ground Radar Halos
      haloMeshes.forEach(h => {{
        const isSel = selectedEvent && selectedEvent.id === h.event.id;
        const rate = isSel ? 3.5 : 1.6;
        const scale = isSel ? 1.4 + Math.sin(elapsed * rate) * 0.35 : 1.0 + Math.sin(elapsed * rate + h.event.riskScore) * 0.18;
        h.ring.scale.set(scale, scale, scale);
      }});

      // 6. Update Real-time Altitude & Resolution HUD
      if (camDist > 3.4) {{
        altTxt.innerText = `ALTITUDE: ORBITAL (${{altKm.toLocaleString()}} km)`;
        resBadge.innerText = "GLOBAL SATELLITE";
        resBadge.style.borderColor = "#38bdf8";
        resBadge.style.color = "#38bdf8";
      }} else if (camDist > 2.6) {{
        altTxt.innerText = `ALTITUDE: STRATOSPHERE (${{altKm.toLocaleString()}} km)`;
        resBadge.innerText = "REGIONAL SATELLITE";
        resBadge.style.borderColor = "#fab219";
        resBadge.style.color = "#fab219";
      }} else if (camDist > 2.18) {{
        altTxt.innerText = `ALTITUDE: TACTICAL (${{altKm.toLocaleString()}} km)`;
        resBadge.innerText = "🛰️ ULTRA-CLEAR SATELLITE ACTIVE";
        resBadge.style.borderColor = "#0ca30c";
        resBadge.style.color = "#4ade80";
      }} else {{
        altTxt.innerText = `ALTITUDE: SURFACE GIS (${{altKm.toLocaleString()}} km)`;
        resBadge.innerText = "🛰️ 2D MAP RESOLUTION";
        resBadge.style.borderColor = "#0ca30c";
        resBadge.style.color = "#4ade80";
      }}

      controls.update();
      renderer.render(scene, camera);
    }}

    // --- Window Listeners & Init ---
    window.addEventListener("resize", () => {{
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
    }});
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("click", onClick);
    window.addEventListener("dblclick", onDoubleClick);

    buildBeams();
    resetToOrbit();
    animate();
  </script>
</body>
</html>
"""
    return html_content




if __name__ == "__main__":
    exported = export_pipeline_events_for_holo_view()
    print(f"Successfully exported {len(exported)} thermal events for 3D Holo-View.")
    if exported:
        print("Sample event:", json.dumps(exported[0], indent=2))

