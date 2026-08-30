"""Export pipeline detections and risk scores into the Holo-View-Maker 3D Globe format.

Transforms regional (detail_gdf, cluster_df) and national (detail_df, events_df)
detections into the `ThermalEvent` JSON schema expected by the React + Three.js
3D globe application in `holo-view-maker`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
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
    """
    if events is None:
        events = load_or_export_holo_events()

    filtered_events = [e for e in events if e.get("riskScore", 0) >= min_risk]
    events_json_str = json.dumps(filtered_events)
    color_by_mode = "risk" if color_by.lower() == "risk" else "category"
    auto_rotate_js = "true" if auto_rotate else "false"
    selected_id_js = f'"{selected_event_id}"' if selected_event_id else "null"

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
    
    /* Cyber / Command Center HUD Overlays */
    .hud {{ position: absolute; z-index: 10; pointer-events: auto; }}
    .hud-header {{ top: 16px; left: 16px; display: flex; flex-direction: column; gap: 4px; pointer-events: none; }}
    .hud-title {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.78rem; font-weight: 600; letter-spacing: 0.12em; color: #4d8fc4; text-transform: uppercase; text-shadow: 0 0 10px rgba(77,143,196,0.6); display: flex; align-items: center; gap: 8px; }}
    .pulse-dot {{ width: 7px; height: 7px; border-radius: 50%; background: #0ca30c; box-shadow: 0 0 8px #0ca30c; animation: pulse 2s infinite; }}
    @keyframes pulse {{ 0%, 100% {{ opacity: 1; transform: scale(1); }} 50% {{ opacity: 0.4; transform: scale(0.85); }} }}
    .hud-subtitle {{ font-size: 0.72rem; color: #9a9da1; font-family: 'IBM Plex Mono', monospace; }}

    .hud-stats {{ top: 16px; right: 16px; display: flex; gap: 10px; }}
    .stat-pill {{ background: rgba(10, 14, 20, 0.85); backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 6px; padding: 6px 12px; text-align: right; box-shadow: 0 4px 14px rgba(0,0,0,0.6); }}
    .stat-pill .lbl {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.58rem; color: #7f8691; text-transform: uppercase; letter-spacing: 0.06em; }}
    .stat-pill .val {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.95rem; font-weight: 600; color: #e8e9ea; }}

    /* Bottom Prompt matching reference image */
    .hud-prompt {{
      bottom: 22px; left: 50%; transform: translateX(-50%);
      pointer-events: none;
      font-family: 'IBM Plex Mono', monospace; font-size: 0.75rem; font-weight: 600;
      letter-spacing: 0.18em; text-transform: uppercase;
      color: #7dd3fc;
      text-shadow: 0 0 12px rgba(56, 189, 248, 0.8), 0 0 24px rgba(56, 189, 248, 0.4);
      background: rgba(4, 8, 15, 0.65); backdrop-filter: blur(8px);
      padding: 6px 18px; border-radius: 20px; border: 1px solid rgba(56, 189, 248, 0.25);
    }}

    /* Detail Panel Card */
    #detail-card {{
      bottom: 16px; right: 16px; width: 310px; max-height: calc(100% - 100px);
      background: rgba(10, 15, 24, 0.92); backdrop-filter: blur(14px);
      border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 8px;
      padding: 14px 16px; box-shadow: 0 8px 30px rgba(0,0,0,0.8), 0 0 20px rgba(56,189,248,0.15);
      display: none; flex-direction: column; gap: 10px; overflow-y: auto;
      transition: all 0.25s ease;
    }}
    #detail-card.active {{ display: flex; }}
    .card-top {{ display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 1px solid rgba(255,255,255,0.08); padding-bottom: 8px; }}
    .card-id {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.88rem; font-weight: 600; color: #e8e9ea; }}
    .card-close {{ cursor: pointer; color: #7f8691; font-size: 1.1rem; line-height: 1; border: none; background: transparent; padding: 0 4px; }}
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

    /* Quick controls overlay */
    .hud-controls {{ top: 72px; left: 16px; display: flex; flex-direction: column; gap: 6px; }}
    .hud-btn {{ background: rgba(10, 15, 24, 0.85); backdrop-filter: blur(6px); border: 1px solid rgba(255, 255, 255, 0.14); color: #e8e9ea; font-family: 'IBM Plex Mono', monospace; font-size: 0.68rem; padding: 5px 10px; border-radius: 4px; cursor: pointer; display: flex; align-items: center; gap: 6px; transition: all 0.15s ease; }}
    .hud-btn:hover {{ background: rgba(56, 189, 248, 0.2); border-color: #38bdf8; color: #ffffff; }}
    .hud-btn.active {{ background: #38bdf8; color: #04060a; font-weight: 600; }}
  </style>
  <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
</head>
<body>
  <div id="canvas-container"></div>

  <!-- HUD Header -->
  <div class="hud hud-header">
    <div class="hud-title"><span class="pulse-dot"></span> SIH26162 · 3D ORBITAL THERMAL RADAR</div>
    <div class="hud-subtitle">Interactive 3D Planetary Energy & Risk Radar</div>
  </div>

  <!-- HUD Stats -->
  <div class="hud hud-stats">
    <div class="stat-pill">
      <div class="lbl">Total Active</div>
      <div class="val" id="stat-total">{len(filtered_events)}</div>
    </div>
    <div class="stat-pill">
      <div class="lbl">Critical Risk</div>
      <div class="val" style="color:#e66767;" id="stat-critical">{sum(1 for e in filtered_events if e.get("riskLevel") == "CRITICAL")}</div>
    </div>
    <div class="stat-pill">
      <div class="lbl">High Risk</div>
      <div class="val" style="color:#ec835a;" id="stat-high">{sum(1 for e in filtered_events if e.get("riskLevel") == "HIGH")}</div>
    </div>
    <div class="stat-pill">
      <div class="lbl">Total FRP</div>
      <div class="val" style="color:#fab219;" id="stat-frp">{sum(e.get("frp", 0) for e in filtered_events):.0f} MW</div>
    </div>
  </div>

  <!-- Quick Floating Controls -->
  <div class="hud hud-controls">
    <button class="hud-btn" id="btn-spin" onclick="toggleSpin()">🔄 Spin: ON</button>
    <button class="hud-btn" id="btn-reset" onclick="resetCamera()">🎯 Focus India</button>
    <button class="hud-btn" id="btn-mode" onclick="toggleColorMode()">🎨 Mode: {color_by_mode.upper()}</button>
  </div>

  <!-- Bottom Monospace Prompt matching reference image -->
  <div class="hud hud-prompt">
    DRAG TO ORBIT &middot; SCROLL TO ZOOM &middot; CLICK A BEAM
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
  </div>

  <script>
    // --- Configuration & Constants ---
    const RAW_EVENTS = {events_json_str};
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

    const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 0.1, 1000);
    camera.position.set(0, 1.4, 4.8);

    const renderer = new THREE.WebGLRenderer({{ antialias: true, alpha: false, powerPreference: "high-performance" }});
    renderer.setSize(window.innerWidth, window.innerHeight);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.25;
    container.appendChild(renderer.domElement);

    const controls = new THREE.OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.minDistance = 2.8;
    controls.maxDistance = 10.0;
    controls.autoRotate = isSpinning;
    controls.autoRotateSpeed = 0.5;

    // --- Starfield Background ---
    const starsGeo = new THREE.BufferGeometry();
    const starCount = 1500;
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

    // --- Photorealistic Lighting (Sun + Soft Rim + Ocean Highlight) ---
    const ambientLight = new THREE.AmbientLight(0xdde8f5, 0.45);
    scene.add(ambientLight);

    const sunLight = new THREE.DirectionalLight(0xfff7ed, 2.5);
    sunLight.position.set(6, 2.8, 4.5);
    scene.add(sunLight);

    const nightRimLight = new THREE.DirectionalLight(0x38bdf8, 0.4);
    nightRimLight.position.set(-6, -2, -4);
    scene.add(nightRimLight);

    // --- Earth Group ---
    const earthGroup = new THREE.Group();
    // Rotate to bring India and Indian Ocean to front-and-center
    earthGroup.rotation.y = ((80 + 180) * Math.PI) / 180 - Math.PI / 2;
    scene.add(earthGroup);

    // Texture Loader with robust fallbacks
    const texLoader = new THREE.TextureLoader();
    texLoader.crossOrigin = "anonymous";

    // 1. Earth Day & Night Mesh
    const earthGeo = new THREE.SphereGeometry(GLOBE_RADIUS, 96, 96);
    
    // High quality procedural Earth canvas fallback texture
    function createProceduralEarthCanvas() {{
      const canvas = document.createElement('canvas');
      canvas.width = 2048;
      canvas.height = 1024;
      const ctx = canvas.getContext('2d');
      // Deep Ocean gradient
      const oceanGrad = ctx.createLinearGradient(0, 0, 0, canvas.height);
      oceanGrad.addColorStop(0, '#0a2342');
      oceanGrad.addColorStop(0.5, '#0d325c');
      oceanGrad.addColorStop(1, '#081c36');
      ctx.fillStyle = oceanGrad;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      
      // Continents representation
      ctx.fillStyle = '#2c4c38';
      // Eurasia & India
      ctx.beginPath();
      ctx.ellipse(1400, 360, 420, 220, 0, 0, Math.PI * 2);
      ctx.fill();
      // Africa
      ctx.beginPath();
      ctx.ellipse(1150, 560, 160, 240, 0.2, 0, Math.PI * 2);
      ctx.fill();
      // Americas
      ctx.beginPath();
      ctx.ellipse(500, 450, 180, 320, -0.2, 0, Math.PI * 2);
      ctx.fill();
      // Australia
      ctx.beginPath();
      ctx.ellipse(1700, 720, 140, 100, 0, 0, Math.PI * 2);
      ctx.fill();
      return new THREE.CanvasTexture(canvas);
    }}

    const defaultDayTex = createProceduralEarthCanvas();
    const earthMat = new THREE.MeshPhongMaterial({{
      map: defaultDayTex,
      specular: new THREE.Color(0x3a6b94),
      shininess: 25,
      bumpScale: 0.05
    }});

    const earthMesh = new THREE.Mesh(earthGeo, earthMat);
    earthGroup.add(earthMesh);

    // Load NASA Blue Marble Texture
    texLoader.load(
      "https://unpkg.com/three-globe/example/img/earth-blue-marble.jpg",
      (tex) => {{
        tex.colorSpace = THREE.SRGBColorSpace;
        tex.anisotropy = 8;
        earthMat.map = tex;
        earthMat.needsUpdate = true;
      }},
      undefined,
      (err) => console.log("Using procedural fallback day texture")
    );

    // City lights on the dark side with AdditiveBlending
    texLoader.load(
      "https://unpkg.com/three-globe/example/img/earth-night.jpg",
      (lightsTex) => {{
        lightsTex.colorSpace = THREE.SRGBColorSpace;
        const lightsMat = new THREE.MeshBasicMaterial({{
          map: lightsTex,
          blending: THREE.AdditiveBlending,
          transparent: true,
          opacity: 0.55,
          depthWrite: false
        }});
        const lightsMesh = new THREE.Mesh(new THREE.SphereGeometry(GLOBE_RADIUS * 1.001, 96, 96), lightsMat);
        earthGroup.add(lightsMesh);
      }}
    );

    // Drifting cloud shell
    let cloudsMesh = null;
    texLoader.load(
      "https://unpkg.com/three-globe/example/img/clouds.png",
      (cloudsTex) => {{
        const cloudsMat = new THREE.MeshLambertMaterial({{
          map: cloudsTex,
          transparent: true,
          opacity: 0.4,
          blending: THREE.AdditiveBlending,
          depthWrite: false
        }});
        cloudsMesh = new THREE.Mesh(new THREE.SphereGeometry(GLOBE_RADIUS * 1.012, 64, 64), cloudsMat);
        earthGroup.add(cloudsMesh);
      }}
    );

    // --- Vibrant Cyan Atmospheric Glow Halo (Matching Reference Image) ---
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
      void main() {{
        vec3 viewDir = normalize(-vPosition);
        float intensity = pow(0.68 - dot(vNormal, viewDir), 2.2);
        vec3 atmosColor = vec3(0.22, 0.74, 0.98); // Vibrant cyan #38bdf8
        gl_FragColor = vec4(atmosColor, intensity * 1.6);
      }}
    `;

    const atmosMaterial = new THREE.ShaderMaterial({{
      vertexShader: atmosVertexShader,
      fragmentShader: atmosFragmentShader,
      blending: THREE.AdditiveBlending,
      side: THREE.BackSide,
      transparent: true,
      depthWrite: false
    }});

    const atmosphereMesh = new THREE.Mesh(new THREE.SphereGeometry(GLOBE_RADIUS * 1.15, 64, 64), atmosMaterial);
    scene.add(atmosphereMesh);

    // Inner subtle atmosphere limb
    const innerAtmosMat = new THREE.ShaderMaterial({{
      vertexShader: atmosVertexShader,
      fragmentShader: `
        varying vec3 vNormal;
        varying vec3 vPosition;
        void main() {{
          vec3 viewDir = normalize(-vPosition);
          float intensity = pow(1.0 - dot(vNormal, viewDir), 3.2);
          gl_FragColor = vec4(0.24, 0.72, 0.98, intensity * 0.45);
        }}
      `,
      blending: THREE.AdditiveBlending,
      side: THREE.FrontSide,
      transparent: true,
      depthWrite: false
    }});
    const innerAtmosMesh = new THREE.Mesh(new THREE.SphereGeometry(GLOBE_RADIUS * 1.003, 64, 64), innerAtmosMat);
    earthGroup.add(innerAtmosMesh);


    // --- Coordinate Graticule (Subtle Lat/Lon Lines) ---
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

    // --- Helper Coordinate Math ---
    function latLonToVec3(lat, lon, radius) {{
      const phi = (90 - lat) * (Math.PI / 180);
      const theta = (lon + 180) * (Math.PI / 180);
      return new THREE.Vector3(
        -radius * Math.sin(phi) * Math.cos(theta),
        radius * Math.cos(phi),
        radius * Math.sin(phi) * Math.sin(theta)
      );
    }}

    // --- Thermal Beams & Markers Construction ---
    const markersGroup = new THREE.Group();
    earthGroup.add(markersGroup);

    const interactiveObjects = [];
    const haloMeshes = [];
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

      RAW_EVENTS.forEach(event => {{
        const pos = latLonToVec3(event.latitude, event.longitude, GLOBE_RADIUS);
        const normal = pos.clone().normalize();
        const quat = new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), normal);

        const height = 0.08 + (event.riskScore / 100) * 0.44;
        const colorHex = getEventColor(event);
        const color = new THREE.Color(colorHex);

        const beamGroup = new THREE.Group();
        beamGroup.position.copy(pos);
        beamGroup.quaternion.copy(quat);
        beamGroup.userData = {{ event }};

        // 1. Vertical Glowing Cylinder Beam
        const cylGeo = new THREE.CylinderGeometry(0.008, 0.016, height, 12);
        const cylMat = new THREE.MeshBasicMaterial({{
          color: color,
          transparent: true,
          opacity: 0.88
        }});
        const cylinder = new THREE.Mesh(cylGeo, cylMat);
        cylinder.position.set(0, height / 2, 0);
        beamGroup.add(cylinder);

        // 2. Glowing Head Sphere on top
        const sphereGeo = new THREE.SphereGeometry(0.028, 16, 16);
        const sphereMat = new THREE.MeshBasicMaterial({{ color: color }});
        const beacon = new THREE.Mesh(sphereGeo, sphereMat);
        beacon.position.set(0, height, 0);
        beamGroup.add(beacon);

        // 3. Middle node bead
        const midNodeGeo = new THREE.SphereGeometry(0.018, 12, 12);
        const midNode = new THREE.Mesh(midNodeGeo, sphereMat);
        midNode.position.set(0, height * 0.5, 0);
        beamGroup.add(midNode);

        // 4. Ground Halo Disc on Earth Surface (Matching Reference Image)
        const ringGeo = new THREE.RingGeometry(0.035, 0.075, 32);
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

        markersGroup.add(beamGroup);
        interactiveObjects.push(cylinder, beacon, ring);
        haloMeshes.push({{ ring, event, baseScale: 1.0 }});

        if (initialSelectedId && event.id === initialSelectedId) {{
          selectEvent(event, beamGroup);
        }}
      }});
    }}

    // --- Raycasting Interaction ---
    const raycaster = new THREE.Raycaster();
    const mouse = new THREE.Vector2();

    function onPointerMove(e) {{
      mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
      mouse.y = -(e.clientY / window.innerHeight) * 2 + 1;
      raycaster.setFromCamera(mouse, camera);
      const intersects = raycaster.intersectObjects(interactiveObjects, false);
      document.body.style.cursor = intersects.length > 0 ? "pointer" : "auto";
    }}

    function onClick(e) {{
      mouse.x = (e.clientX / window.innerWidth) * 2 - 1;
      mouse.y = -(e.clientY / window.innerHeight) * 2 + 1;
      raycaster.setFromCamera(mouse, camera);
      const intersects = raycaster.intersectObjects(interactiveObjects, false);
      if (intersects.length > 0) {{
        const hit = intersects[0].object;
        const beamGroup = hit.parent;
        if (beamGroup && beamGroup.userData && beamGroup.userData.event) {{
          selectEvent(beamGroup.userData.event, beamGroup);
        }}
      }}
    }}

    function selectEvent(event, groupMesh) {{
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
        focusOnLatLon(event.latitude, event.longitude);
      }}
    }}

    function closeCard() {{
      document.getElementById("detail-card").classList.remove("active");
      selectedEvent = null;
      selectedMesh = null;
    }}

    function focusOnLatLon(lat, lon) {{
      isSpinning = false;
      controls.autoRotate = false;
      document.getElementById("btn-spin").innerText = "🔄 Spin: OFF";
      
      const targetPos = latLonToVec3(lat, lon, 4.6);
      const startPos = camera.position.clone();
      let progress = 0;
      function anim() {{
        progress += 0.05;
        camera.position.lerpVectors(startPos, targetPos, Math.min(progress, 1));
        controls.update();
        if (progress < 1) requestAnimationFrame(anim);
      }}
      anim();
    }}

    function resetCamera() {{
      camera.position.set(0, 1.4, 4.8);
      controls.target.set(0, 0, 0);
      controls.update();
    }}

    function toggleSpin() {{
      isSpinning = !isSpinning;
      controls.autoRotate = isSpinning;
      document.getElementById("btn-spin").innerText = `🔄 Spin: ${{isSpinning ? "ON" : "OFF"}}`;
    }}

    function toggleColorMode() {{
      colorByMode = colorByMode === "category" ? "risk" : "category";
      document.getElementById("btn-mode").innerText = `🎨 Mode: ${{colorByMode.toUpperCase()}}`;
      buildBeams();
      if (selectedEvent) selectEvent(selectedEvent, selectedMesh);
    }}

    // --- Animation Loop ---
    const clock = new THREE.Clock();
    function animate() {{
      requestAnimationFrame(animate);
      const delta = clock.getDelta();
      const elapsed = clock.getElapsedTime();

      // Rotate clouds layer slowly
      if (cloudsMesh) {{
        cloudsMesh.rotation.y += delta * 0.015;
      }}

      // Pulsate Ground Halos
      haloMeshes.forEach(h => {{
        const isSel = selectedEvent && selectedEvent.id === h.event.id;
        const rate = isSel ? 3.5 : 1.6;
        const scale = isSel ? 1.4 + Math.sin(elapsed * rate) * 0.35 : 1.0 + Math.sin(elapsed * rate + h.event.riskScore) * 0.16;
        h.ring.scale.set(scale, scale, scale);
      }});

      controls.update();
      renderer.render(scene, camera);
    }}

    // --- Init ---
    window.addEventListener("resize", () => {{
      camera.aspect = window.innerWidth / window.innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(window.innerWidth, window.innerHeight);
    }});
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("click", onClick);

    buildBeams();
    resetCamera();
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

