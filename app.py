"""THERMAL INTELLIGENCE — command-center dashboard for SIH26162.

AI-assisted early-warning and prioritization platform for industrial fires
and persistent thermal sources. This is NOT an autonomous system that
confirms fires, and satellite detection is NOT ground truth — see the
"Requires Verification" category and every risk/confidence figure's own
caveats.

Run with: streamlit run app.py
"""
from __future__ import annotations

import json

import folium
import geopandas as gpd
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from folium.plugins import Fullscreen, MarkerCluster, TimestampedGeoJson
from streamlit_folium import st_folium

import config
from src import pipeline, store
from src.firms.fetch import FirmsAuthError, check_map_key
from src.processing.spatial_clusters import find_spatial_clusters
from src.utils.event_id import event_id_for_cell
from src.utils.export_3d_globe import (
    export_pipeline_events_for_holo_view,
    load_or_export_holo_events,
)

TIMELAPSE_MAX_POINTS = 600

st.set_page_config(page_title="Thermal Intelligence", layout="wide", page_icon=":material/local_fire_department:", initial_sidebar_state="expanded")

CATEGORY_COLORS = {
    "Likely Industrial Fire": "#3987e5",
    "Persistent Non-Industrial Thermal Source": "#d95926",
    "Transient Industrial Flare": "#199e70",
    "Likely Agricultural Burning": "#c98500",
    "Sun Glint / False Positive": "#d55181",
    "Likely Wildfire": "#008300",
    "Persistent Industrial Activity": "#9085e9",
    "Requires Verification": "#e66767",
}
RISK_COLORS = {"LOW": "#0ca30c", "MODERATE": "#fab219", "HIGH": "#ec835a", "CRITICAL": "#e66767"}
STATUS_COLORS = {
    "NEW": "#4d8fc4", "RECURRING": "#9a9da1", "PERSISTENT": "#fab219",
    "HIGH RISK": "#ec835a", "CRITICAL": "#e66767", "RESOLVED/INACTIVE": "#6b6e72",
}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap');
:root{
  --ink:#e8e9ea; --ink2:#9a9da1; --muted:#6b6e72;
  --line:rgba(255,255,255,.08); --line-strong:rgba(255,255,255,.16);
  --page:#0c0d0e; --surface:#131415; --accent:#4d8fc4;
  --accent-low:#0ca30c; --accent-moderate:#fab219; --accent-high:#ec835a; --accent-critical:#e66767;
  --accent-violet:#9085e9;
}
html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"], p, label {
  font-family:'IBM Plex Sans',system-ui,-apple-system,'Segoe UI',sans-serif !important;
}
.mono{ font-family:'IBM Plex Mono',ui-monospace,monospace; }

.header{ display:flex; justify-content:space-between; align-items:flex-end; flex-wrap:wrap; gap:1rem;
  padding-bottom:1.1rem; margin-bottom:1.3rem; border-bottom:1px solid var(--line-strong); }
.header .eyebrow{ font-family:'IBM Plex Mono',monospace; font-size:.7rem; font-weight:500;
  letter-spacing:.10em; text-transform:uppercase; color:var(--accent); margin-bottom:.5rem; }
.header h1{ margin:0 0 .4rem; font-size:1.45rem; font-weight:600; letter-spacing:-.005em; color:var(--ink); }
.header .sub{ margin:0; color:var(--ink2); font-size:.83rem; max-width:52ch; }
.header .meta{ text-align:right; font-family:'IBM Plex Mono',monospace; font-size:.72rem; color:var(--ink2); line-height:1.7; }
.dot{ display:inline-block; width:7px; height:7px; border-radius:50%; margin-right:5px; }
.dot.live{ background:var(--accent-low); } .dot.demo{ background:var(--accent-moderate); } .dot.stale{ background:var(--muted); }

.statrow{ display:grid; grid-template-columns:repeat(4,1fr); border:1px solid var(--line); border-radius:4px; overflow:hidden; margin-bottom:.7rem; }
.statrow + .statrow{ border-top:none; }
.stat{ padding:.7rem 1rem; border-right:1px solid var(--line); background:var(--surface); border-top:2px solid var(--stat-accent, transparent); }
.stat:last-child{ border-right:none; }
.stat.flag{ border-top-color:var(--stat-accent, var(--accent)); }
.stat .lbl{ font-family:'IBM Plex Mono',monospace; font-size:.63rem; letter-spacing:.06em; text-transform:uppercase; color:var(--muted); margin-bottom:.3rem; }
.stat .val{ font-family:'IBM Plex Mono',monospace; font-size:1.25rem; font-weight:600; color:var(--ink); font-variant-numeric:tabular-nums; }
.stat-icon{ font-size:.85rem; vertical-align:-2px; color:var(--stat-accent, var(--muted)); }

.sec-hdr{ font-family:'IBM Plex Mono',monospace; font-size:.7rem; font-weight:500;
  letter-spacing:.08em; text-transform:uppercase; color:var(--ink2);
  padding-bottom:.5rem; margin-bottom:.8rem; border-bottom:1px solid var(--line); }
.sec-hdr-icon{ font-size:.95rem; vertical-align:-2px; color:var(--accent); }

.alertbar{ display:flex; align-items:center; justify-content:space-between; gap:1rem;
  border:1px solid rgba(230,103,103,.35); border-left:3px solid var(--accent-critical); background:rgba(230,103,103,.08);
  border-radius:6px; padding:.8rem 1.1rem; margin-bottom:1rem; }
.alertbar .txt{ font-size:.88rem; color:var(--ink); }
.alertbar .txt b{ font-variant-numeric:tabular-nums; }
.alertcard{ border:1px solid var(--line); border-left:3px solid var(--sev, var(--accent)); background:var(--surface);
  border-radius:6px; padding:.7rem .95rem; margin-bottom:.5rem; }
.alertcard .title{ font-weight:600; font-size:.85rem; color:var(--ink); }
.alertcard .meta{ font-family:'IBM Plex Mono',monospace; font-size:.72rem; color:var(--ink2); margin-top:.3rem; line-height:1.7; }

.pill{ display:inline-flex; align-items:center; gap:5px; font-family:'IBM Plex Mono',monospace; font-size:.68rem;
  font-weight:600; letter-spacing:.03em; padding:.18rem .55rem; border-radius:99px; text-transform:uppercase; }
.pill::before{ content:""; width:6px; height:6px; border-radius:50%; background:currentColor; }
.pill.has-icon::before{ content:none; }
.pill-icon{ font-size:.85em; }

.badge-demo{ font-family:'IBM Plex Mono',monospace; font-size:.68rem; font-weight:600; letter-spacing:.05em;
  color:var(--accent-moderate); border:1px solid rgba(250,178,25,.4); background:rgba(250,178,25,.1); border-radius:4px; padding:.2rem .6rem; }

.panel{ border:1px solid var(--line); border-radius:6px; background:var(--surface); padding:1rem 1.15rem; }
.panel .row{ display:flex; justify-content:space-between; padding:.35rem 0; border-bottom:1px solid var(--line); font-size:.83rem; }
.panel .row:last-child{ border-bottom:none; }
.panel .row .k{ color:var(--ink2); } .panel .row .v{ color:var(--ink); font-family:'IBM Plex Mono',monospace; font-variant-numeric:tabular-nums; text-align:right; }
.evidence{ font-size:.82rem; color:var(--ink2); padding:.25rem 0; border-bottom:1px dashed var(--line); }
.evidence:last-child{ border-bottom:none; }
.evidence::before{ content:"\2713  "; color:var(--accent-low); }

.side-label{ font-family:'IBM Plex Mono',monospace; font-size:.68rem; font-weight:500;
  letter-spacing:.09em; text-transform:uppercase; color:var(--muted); margin:.4rem 0 .6rem; }
section[data-testid="stSidebar"]{ border-right:1px solid var(--line); }

[data-testid="stButton"] button, [data-testid="stDownloadButton"] button{
  border-radius:4px !important; font-weight:500 !important; letter-spacing:.03em !important;
  font-size:.76rem !important; text-transform:uppercase; font-family:'IBM Plex Mono',monospace !important;
  transition:filter .12s ease !important; }
[data-testid="stButton"] button:hover, [data-testid="stDownloadButton"] button:hover{ filter:brightness(1.15); }

.legend-chip{ display:inline-flex;align-items:center;gap:6px;font-size:.76rem;margin:2px 10px 2px 0;color:var(--ink2); }
.legend-dot{ width:9px;height:9px;border-radius:50%;display:inline-block;flex:none; }

.caveat{ font-size:.76rem; color:var(--muted); border-top:1px dashed var(--line); padding-top:.5rem; margin-top:.6rem; line-height:1.6; }

.brand{ font-family:'IBM Plex Mono',monospace; font-size:.86rem; font-weight:600; letter-spacing:.05em; color:var(--ink); }
.brand-sub{ font-family:'IBM Plex Mono',monospace; font-size:.6rem; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); margin-top:.15rem; margin-bottom:.2rem; }

.topbar-brand h1{ margin:0 0 .2rem; font-size:1.18rem; font-weight:600; letter-spacing:-.005em; color:var(--ink); }
.topbar-brand .eyebrow{ font-family:'IBM Plex Mono',monospace; font-size:.62rem; font-weight:500; letter-spacing:.09em;
  text-transform:uppercase; color:var(--accent); margin-bottom:.3rem; }
.topbar-brand .sub{ margin:0; color:var(--ink2); font-size:.74rem; }
.topbar-meta{ font-family:'IBM Plex Mono',monospace; font-size:.7rem; color:var(--ink2); line-height:1.6; padding-top:.15rem; }
.topbar-rule{ border:none; border-top:1px solid var(--line-strong); margin:.9rem 0 1.2rem; }

section[data-testid="stSidebar"] [data-testid="stButton"] button{
  justify-content:flex-start; text-align:left; text-transform:none; font-weight:500 !important;
}

.funnel{ display:flex; align-items:stretch; gap:.4rem; margin-bottom:1rem; }
.funnel-step{ flex:1; min-width:0; border:1px solid var(--line); border-radius:6px; background:var(--surface);
  padding:.65rem .8rem; border-top:2px solid var(--line); }
.funnel-step.on{ border-top-color:var(--accent); }
.funnel-step.off{ opacity:.55; }
.funnel-step .fnum{ font-family:'IBM Plex Mono',monospace; font-size:.62rem; letter-spacing:.08em; color:var(--muted); }
.funnel-step .ftitle{ font-weight:600; font-size:.8rem; color:var(--ink); margin:.15rem 0 .3rem; }
.funnel-step .fmetric{ font-family:'IBM Plex Mono',monospace; font-size:1rem; font-weight:600; color:var(--ink); }
.funnel-step .fsub{ font-size:.68rem; color:var(--ink2); margin-top:.1rem; }
.funnel-arrow{ display:flex; align-items:center; color:var(--muted); font-size:1rem; flex:0 0 auto; padding:0 .1rem; }
@keyframes pulse-glow { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.45; transform: scale(0.96); } }
</style>
"""


# ---------------------------------------------------------------- helpers --

def _section_header(text: str, icon: str | None = None, icon_color: str | None = None):
    icon_html = ""
    if icon:
        style = f' style="color:{icon_color};"' if icon_color else ""
        icon_html = f'<span class="sec-hdr-icon"{style}>:material/{icon}:</span> '
    st.markdown(f'<div class="sec-hdr">{icon_html}{text}</div>', unsafe_allow_html=True)


def _format_satellites(value) -> str:
    """satellites is a real list on a fresh pipeline run, but comes back as a
    Python-list-repr string after a round-trip through the cluster_summary
    CSV cache — handle both without erroring."""
    if isinstance(value, (list, tuple, set)):
        items = value
    elif isinstance(value, str) and value.strip().startswith("["):
        import ast
        try:
            items = ast.literal_eval(value)
        except (ValueError, SyntaxError):
            items = [value]
    elif value is None or (isinstance(value, float) and pd.isna(value)):
        items = []
    else:
        items = [value]
    return ", ".join(str(i) for i in items) if items else "n/a"


def _pill(text: str, color: str, icon: str | None = None) -> str:
    cls = "pill has-icon" if icon else "pill"
    icon_html = f'<span class="pill-icon">:material/{icon}:</span>' if icon else ""
    return f'<span class="{cls}" style="color:{color};background:{color}22;border:1px solid {color}55;">{icon_html}{text}</span>'


def _stat_row(cells: list[tuple]):
    """Each cell is (label, value, flag) or optionally (label, value, flag, icon, accent_color)."""
    parts = []
    for cell in cells:
        label, value, flag = cell[0], cell[1], cell[2]
        icon = cell[3] if len(cell) > 3 else None
        accent = cell[4] if len(cell) > 4 else None
        icon_html = f'<span class="stat-icon">:material/{icon}:</span> ' if icon else ""
        style_attr = f' style="--stat-accent:{accent}"' if accent else ""
        parts.append(
            f'<div class="stat{" flag" if flag else ""}"{style_attr}>'
            f'<div class="lbl">{icon_html}{label}</div><div class="val">{value}</div></div>'
        )
    st.markdown('<div class="statrow">' + "".join(parts) + "</div>", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def _load_cached_detail() -> gpd.GeoDataFrame | None:
    if not config.CLASSIFIED_GEOJSON.exists():
        return None
    gdf = gpd.read_file(config.CLASSIFIED_GEOJSON)
    gdf["acq_date"] = pd.to_datetime(gdf["acq_date"])
    return gdf


@st.cache_data(show_spinner=False)
def _load_cached_clusters() -> pd.DataFrame:
    path = config.PROCESSED_DIR / "cluster_summary.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    for c in ("first_detected", "last_detected"):
        if c in df.columns:
            df[c] = pd.to_datetime(df[c])
    return df


@st.cache_data(show_spinner=False)
def _load_cached_alerts() -> list[dict]:
    path = config.PROCESSED_DIR / "alerts.json"
    if not path.exists():
        return []
    return json.loads(path.read_text())


def run_and_cache(demo_mode: bool, api_key: str | None):
    with st.spinner("Running pipeline: fetch → clean → geospatial join → classify → risk → alerts..."):
        try:
            info = pipeline.run_pipeline(demo_mode=demo_mode, api_key=api_key)
        except Exception as exc:
            st.error(f"Pipeline run failed: {exc}", icon=":material/cancel:")
            return
    st.session_state["run_info"] = {k: v for k, v in info.items() if k not in ("detail_gdf", "cluster_df")}
    st.session_state["run_info"]["n_alerts"] = len(info["alerts"])
    _load_cached_detail.clear()
    _load_cached_clusters.clear()
    _load_cached_alerts.clear()

    # Automated critical alert message dispatch
    if st.session_state.get("alert_auto_dispatch", config.ALERT_AUTO_DISPATCH_CRITICAL):
        from src.alerts import messages as alert_messages
        phone = st.session_state.get("alert_phone", config.ALERT_RECIPIENT_PHONE)
        crit_results = alert_messages.send_batch_critical_alerts(info["alerts"], phone=phone)
        if crit_results:
            st.toast(f"{len(crit_results)} Critical Alert Message(s) Auto-Dispatched to {phone}", icon=":material/sms:")


    # Synchronize live pipeline events with 3D Holo Globe
    try:
        exported_3d = export_pipeline_events_for_holo_view(info.get("detail_gdf"), info.get("cluster_df"))
        st.session_state["holo_events_count"] = len(exported_3d)
        st.session_state["holo_last_synced"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    except Exception as exc:
        print(f"[app] 3D globe export error: {exc}")

    st.success(f"Done — {len(info['detail_gdf'])} detections, {len(info['cluster_df'])} clusters, {len(info['alerts'])} alerts (3D Holo Globe updated).", icon=":material/check_circle:")


def recompute_risk_and_cache(weights: dict):
    """Re-score already-loaded detail/cluster data with custom risk
    weights — no re-fetch, re-geospatial-join, or re-training needed, only
    risk_score/risk_level/status/alerts are recomputed and re-cached."""
    from src.alerts import engine as alert_engine
    from src.risk import scoring as risk_scoring
    from src.utils import status as status_utils

    gdf = _load_cached_detail()
    cluster_df = _load_cached_clusters()
    if gdf is None or gdf.empty:
        st.warning("No data loaded yet — run the pipeline first.", icon=":material/warning:")
        return

    gdf = risk_scoring.compute_risk(gdf, weights=weights)
    risk_by_cell = gdf.groupby("grid_cell")["risk_score"].max().rename("risk_score")
    cluster_df = cluster_df.drop(columns=["risk_score", "risk_level"], errors="ignore").merge(
        risk_by_cell, on="grid_cell", how="left"
    )
    cluster_df["risk_level"] = cluster_df["risk_score"].apply(risk_scoring.risk_level)
    cluster_df = status_utils.assign_status(cluster_df)
    alerts = alert_engine.generate_alerts(gdf, cluster_df)

    export = gdf.copy()
    export["acq_date"] = export["acq_date"].astype(str)
    export.to_file(config.CLASSIFIED_GEOJSON, driver="GeoJSON")
    export.drop(columns="geometry").to_csv(config.CLASSIFIED_CSV, index=False)
    cluster_export: pd.DataFrame = cluster_df.copy()
    cluster_export["first_detected"] = cluster_export["first_detected"].astype(str)
    cluster_export["last_detected"] = cluster_export["last_detected"].astype(str)
    cluster_export.to_csv(config.PROCESSED_DIR / "cluster_summary.csv", index=False)
    (config.PROCESSED_DIR / "alerts.json").write_text(json.dumps(alerts, default=str))

    _load_cached_detail.clear()
    _load_cached_clusters.clear()
    _load_cached_alerts.clear()

    # Automated critical alert message dispatch
    if st.session_state.get("alert_auto_dispatch", config.ALERT_AUTO_DISPATCH_CRITICAL):
        from src.alerts import messages as alert_messages
        phone = st.session_state.get("alert_phone", config.ALERT_RECIPIENT_PHONE)
        crit_results = alert_messages.send_batch_critical_alerts(alerts, phone=phone)
        if crit_results:
            st.toast(f"{len(crit_results)} Critical Alert Message(s) Auto-Dispatched to {phone}", icon=":material/sms:")


    # Synchronize recomputed risk events with 3D Holo Globe
    try:
        exported_3d = export_pipeline_events_for_holo_view(gdf, cluster_df)
        st.session_state["holo_events_count"] = len(exported_3d)
        st.session_state["holo_last_synced"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    except Exception as exc:
        print(f"[app] 3D globe export error: {exc}")

    st.success(f"Risk scores recomputed with custom weights — {len(alerts)} alerts regenerated (3D Holo Globe updated).", icon=":material/check_circle:")


def run_national_and_cache(demo_mode: bool, api_key: str | None):
    from src.national.pipeline import run_national_pipeline
    with st.spinner("Running national pipeline: fetch (latest observations) → clean → grid → state tagging → risk..."):
        try:
            info = run_national_pipeline(demo_mode=demo_mode, api_key=api_key)
        except Exception as exc:
            st.error(f"National pipeline run failed: {exc}", icon=":material/cancel:")
            return
    info["run_at"] = pd.Timestamp.now()
    st.session_state["national_info"] = info

    # Synchronize national pipeline events with 3D Holo Globe
    try:
        exported_3d = export_pipeline_events_for_holo_view(
            events_df=info.get("events_df"),
            national_detail_df=info.get("detail_df"),
        )
        st.session_state["holo_events_count"] = len(exported_3d)
        st.session_state["holo_last_synced"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    except Exception as exc:
        print(f"[app] 3D globe national export error: {exc}")

    st.success(f"Done — {info['n_observations']} observations, {info['n_events']} events across "
               f"{info['state_summary']['state'].notna().sum() if not info['state_summary'].empty else 0} states (3D Holo Globe updated).",
               icon=":material/check_circle:")



# ------------------------------------------------------------------- map --

FONT_STACK = "'IBM Plex Sans',system-ui,-apple-system,'Segoe UI',sans-serif"
MONO_STACK = "'IBM Plex Mono',ui-monospace,monospace"

CLUSTER_ICON_JS = """
function(cluster) {
    var count = cluster.getChildCount();
    var size = count < 10 ? 32 : count < 50 ? 38 : 46;
    return new L.DivIcon({
        html: '<div class="thermal-cluster-inner">' + count + '</div>',
        className: 'thermal-cluster-icon',
        iconSize: L.point(size, size)
    });
}
"""

MAP_CHROME_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=swap');
.material-symbols-rounded {{
  font-family:'Material Symbols Rounded'; font-weight:normal; font-style:normal;
  line-height:1; letter-spacing:normal; text-transform:none; display:inline-block;
  white-space:nowrap; word-wrap:normal; direction:ltr; vertical-align:middle;
  -webkit-font-smoothing:antialiased;
  font-variation-settings:'FILL' 0,'wght' 400,'GRAD' 0,'opsz' 24;
}}
.thermal-cluster-icon {{ background: transparent !important; border: none !important; }}
.thermal-cluster-inner {{
    width:100%; height:100%; display:flex; align-items:center; justify-content:center;
    background:#131415; border:2px solid #4d8fc4; border-radius:50%; color:#e8e9ea;
    font-family:{MONO_STACK}; font-weight:600; font-size:12px; box-shadow:0 2px 10px rgba(0,0,0,.55);
}}
.leaflet-popup-content-wrapper {{ background:#131415 !important; color:#e8e9ea !important;
    border-radius:8px !important; box-shadow:0 4px 18px rgba(0,0,0,.5) !important; }}
.leaflet-popup-tip {{ background:#131415 !important; }}
.leaflet-control-layers, .leaflet-bar a {{ background:#131415 !important; color:#e8e9ea !important;
    border-color:rgba(255,255,255,.12) !important; }}
.leaflet-control-layers-toggle {{ filter:invert(1) brightness(1.5); }}
.leaflet-control-scale-line {{ background:rgba(19,20,21,.8) !important; color:#e8e9ea !important;
    border-color:rgba(255,255,255,.35) !important; font-family:{MONO_STACK}; }}
</style>
"""


def _add_base_layers(m: folium.Map):
    folium.TileLayer("CartoDB dark_matter", name="Dark", control=True).add_to(m)
    folium.TileLayer("CartoDB positron", name="Light", control=True).add_to(m)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri, Maxar, Earthstar Geographics", name="Satellite", control=True,
    ).add_to(m)


def _add_map_chrome(m: folium.Map, legend_html: str | None = None):
    """Shared premium-map furniture: matching cluster icons/popups, a
    fullscreen control, a base-layer switcher, and (optionally) a legend —
    kept minimal per the "large map, minimal controls" design goal."""
    m.get_root().html.add_child(folium.Element(MAP_CHROME_CSS))  # pyright: ignore[reportAttributeAccessIssue]
    Fullscreen(position="topright").add_to(m)
    folium.LayerControl(position="topright", collapsed=True).add_to(m)
    if legend_html:
        m.get_root().html.add_child(folium.Element(legend_html))  # pyright: ignore[reportAttributeAccessIssue]


def _legend_html(title: str, items: dict[str, str]) -> str:
    chips = "".join(
        f'<span class="legend-chip"><i class="legend-dot" style="background:{c}"></i>{label}</span>'
        for label, c in items.items()
    )
    return f"""
    <div style="position:fixed;bottom:26px;left:26px;z-index:9999;background:#131415;
        padding:10px 14px;border-radius:8px;border:1px solid rgba(255,255,255,.10);
        box-shadow:0 4px 16px rgba(0,0,0,.5);font-family:{FONT_STACK};max-width:230px;">
        <b style="color:#e8e9ea;font-size:11px;letter-spacing:.06em;text-transform:uppercase;font-family:{MONO_STACK};">{title}</b><br>{chips}
    </div>"""


def build_map(gdf: gpd.GeoDataFrame, label_field: str, color_by: str) -> folium.Map:
    center_lat = (config.BBOX["min_lat"] + config.BBOX["max_lat"]) / 2
    center_lon = (config.BBOX["min_lon"] + config.BBOX["max_lon"]) / 2
    m = folium.Map(location=[center_lat, center_lon], zoom_start=8, tiles=None, control_scale=True)
    _add_base_layers(m)

    folium.Rectangle(
        bounds=[[config.BBOX["min_lat"], config.BBOX["min_lon"]], [config.BBOX["max_lat"], config.BBOX["max_lon"]]],
        color="#4d8fc4", weight=1, fill=False, dash_array="4", tooltip="Target region bounding box",
    ).add_to(m)

    cluster = MarkerCluster(disableClusteringAtZoom=12, maxClusterRadius=45,
                             icon_create_function=CLUSTER_ICON_JS).add_to(m)

    for _, row in gdf.iterrows():
        if color_by == "risk":
            color = RISK_COLORS.get(row.get("risk_level", ""), "#888888")
        else:
            color = CATEGORY_COLORS.get(row[label_field], "#888888")

        risk_pct = max(0, min(100, row.get("risk_score", 0)))
        popup_html = (
            f'<div style="font-family:{FONT_STACK};font-size:12.5px;line-height:1.6;padding:2px;min-width:200px;">'
            f"<b style='color:{color}'>{row[label_field]}</b><br>"
            f"<span style='color:#9a9da1;'>Risk {row.get('risk_score', 0):.0f}/100 ({row.get('risk_level', '?')})</span>"
            f'<div style="height:4px;background:rgba(255,255,255,.1);border-radius:2px;margin:.3rem 0 .5rem;">'
            f'<div style="height:100%;width:{risk_pct}%;background:{RISK_COLORS.get(row.get("risk_level", ""), "#888")};border-radius:2px;"></div></div>'
            f"Date: {row['acq_date']} ({row.get('daynight', '?')})<br>"
            f"FRP: {row['frp']:.1f} MW &middot; Confidence: {row['confidence_numeric']:.0f}<br>"
            f"Persistence: {row['persistence_days']} days &middot; Zone: {row['zone_type']}<br>"
            f"<span style='font-family:{MONO_STACK};color:#6b6e72;font-size:11px;'>{row.get('grid_cell', '?')}</span>"
            f"</div>"
        )
        radius = 4 + min(row["frp"], 40) / 10
        if row.get("is_persistent"):
            folium.CircleMarker(  # halo/ring for persistent sources
                location=[row.geometry.y, row.geometry.x], radius=radius + 4,
                color=color, weight=1.5, fill=False, opacity=0.6,
            ).add_to(cluster)
        folium.CircleMarker(
            location=[row.geometry.y, row.geometry.x], radius=radius, color=color,
            fill=True, fill_color=color, fill_opacity=0.85, weight=1,
            popup=folium.Popup(popup_html, max_width=280),
        ).add_to(cluster)

    legend_source = CATEGORY_COLORS if color_by != "risk" else RISK_COLORS
    legend_title = "Classification" if color_by != "risk" else "Risk Level"
    _add_map_chrome(m, _legend_html(legend_title, legend_source))
    return m


def build_timelapse_map(gdf: gpd.GeoDataFrame, label_field: str) -> folium.Map:
    if len(gdf) > TIMELAPSE_MAX_POINTS:
        gdf = gdf.sort_values("acq_date").tail(TIMELAPSE_MAX_POINTS)
    center_lat = (config.BBOX["min_lat"] + config.BBOX["max_lat"]) / 2
    center_lon = (config.BBOX["min_lon"] + config.BBOX["max_lon"]) / 2
    m = folium.Map(location=[center_lat, center_lon], zoom_start=8, tiles=None, control_scale=True)
    _add_base_layers(m)
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [row.geometry.x, row.geometry.y]},
            "properties": {
                "time": row["acq_date"].strftime("%Y-%m-%d"), "icon": "circle",
                "iconstyle": {
                    "fillColor": CATEGORY_COLORS.get(row[label_field], "#888888"),
                    "color": CATEGORY_COLORS.get(row[label_field], "#888888"),
                    "fillOpacity": 0.85, "radius": 5 + min(row["frp"], 40) / 8,
                },
                "popup": f"<b>{row[label_field]}</b><br>{row['acq_date'].date()} · FRP {row['frp']:.1f} MW",
            },
        }
        for _, row in gdf.iterrows()
    ]
    TimestampedGeoJson(
        {"type": "FeatureCollection", "features": features}, period="P1D", duration="P1D",
        add_last_point=False, auto_play=False, loop=False, max_speed=4, loop_button=True,
        date_options="YYYY-MM-DD", time_slider_drag_update=True,
    ).add_to(m)
    _add_map_chrome(m, _legend_html("Classification", CATEGORY_COLORS))
    return m


# ------------------------------------------------------- investigation panel --

def render_investigation_panel(cluster_row: pd.Series, detail_rows: pd.DataFrame, analyst_mode: bool):
    label = cluster_row.get("dominant_label", "Requires Verification")
    color = CATEGORY_COLORS.get(label, "#888888")
    risk = cluster_row.get("risk_score", 0)
    risk_lvl = cluster_row.get("risk_level", "LOW")
    status = cluster_row.get("status", "")

    event_id = cluster_row.get("event_id", cluster_row["grid_cell"])
    st.markdown(f"#### THERMAL EVENT — `{event_id}`", unsafe_allow_html=False)
    st.caption(f"Grid cell {cluster_row['grid_cell']}")
    top1, top2, top3, top4 = st.columns(4)
    top1.markdown(_pill(label, color), unsafe_allow_html=True)
    top2.markdown(_pill(f"RISK {risk:.0f}/100", RISK_COLORS.get(risk_lvl, "#888")), unsafe_allow_html=True)
    top3.markdown(_pill(risk_lvl, RISK_COLORS.get(risk_lvl, "#888")), unsafe_allow_html=True)
    top4.markdown(_pill(status, STATUS_COLORS.get(status, "#888")), unsafe_allow_html=True)
    if bool(cluster_row.get("is_anomalous")):
        st.markdown(_pill("THERMAL ANOMALY DETECTED", "#e66767", icon="warning"), unsafe_allow_html=True)

    window_col = f"persistence_{config.PERSISTENCE_DEFAULT_WINDOW_DAYS}d"
    rows_html = "".join(
        f'<div class="row"><span class="k">{k}</span><span class="v">{v}</span></div>'
        for k, v in [
            ("Latitude / Longitude", f"{cluster_row['latitude']:.4f}, {cluster_row['longitude']:.4f}"),
            ("First Detection", str(pd.Timestamp(cluster_row["first_detected"]).date())),
            ("Last Detection", str(pd.Timestamp(cluster_row["last_detected"]).date())),
            (f"Persistence ({config.PERSISTENCE_DEFAULT_WINDOW_DAYS}d window)", f"{cluster_row.get(window_col, 0)} days"),
            ("Detection Count", int(cluster_row.get("detection_count", 0))),
            ("Average FRP", f"{cluster_row.get('avg_frp', 0):.1f} MW"),
            ("Maximum FRP", f"{cluster_row.get('max_frp', 0):.1f} MW"),
            ("Industrial Distance", f"{cluster_row.get('industrial_distance_km', float('nan')):.2f} km" if pd.notna(cluster_row.get("industrial_distance_km")) else "n/a"),
            ("Mine Distance", f"{cluster_row.get('mine_distance_km', float('nan')):.2f} km" if pd.notna(cluster_row.get("mine_distance_km")) else "n/a"),
            ("Power Plant Distance", f"{cluster_row.get('power_distance_km', float('nan')):.2f} km" if pd.notna(cluster_row.get("power_distance_km")) else "n/a"),
            ("Forest Distance", f"{cluster_row.get('forest_distance_km', float('nan')):.2f} km" if pd.notna(cluster_row.get("forest_distance_km")) else "n/a"),
            ("Water Body Distance", f"{cluster_row.get('water_distance_km', float('nan')):.2f} km" if pd.notna(cluster_row.get("water_distance_km")) else "n/a"),
            ("In Agricultural Zone", "Yes" if bool(cluster_row.get("in_agricultural_zone")) else "No"),
            ("Zone Type", cluster_row.get("zone_type", "?")),
            ("Zone Kind", cluster_row.get("zone_kind", "?")),
            ("Satellites Detected", _format_satellites(cluster_row.get("satellites"))),
        ]
    )
    st.markdown(f'<div class="panel">{rows_html}</div>', unsafe_allow_html=True)

    st.markdown("**Why this classification?**")
    evidence = str(detail_rows.iloc[-1].get("rule_evidence", "")) if not detail_rows.empty else ""
    for item in evidence.split("|"):
        if item.strip():
            st.markdown(f'<div class="evidence">{item}</div>', unsafe_allow_html=True)
    if not detail_rows.empty:
        st.caption(f"Rule: {detail_rows.iloc[-1].get('rule_reason', '')}")
        ml_label = detail_rows.iloc[-1].get("ml_label")
        ml_conf = detail_rows.iloc[-1].get("ml_confidence", 0.5)
        if pd.notna(ml_label) and pd.notna(ml_conf):
            ml_conf = float(ml_conf)
            st.caption(f"ML model agrees: **{ml_label}** (model confidence {ml_conf:.0%})" if ml_label == label
                       else f"ML model instead predicts: **{ml_label}** (model confidence {ml_conf:.0%}) — worth a second look")

    if bool(cluster_row.get("has_baseline")):
        st.markdown("**What Changed?**")
        baseline = cluster_row.get("frp_baseline_mean", float("nan"))
        latest = cluster_row.get("latest_frp", float("nan"))
        change_pct = cluster_row.get("frp_change_pct", 0.0)
        zscore = cluster_row.get("frp_zscore", 0.0)
        arrow = "↑" if change_pct > 0 else ("↓" if change_pct < 0 else "→")
        wc1, wc2, wc3 = st.columns(3)
        wc1.markdown(f'<div class="stat"><div class="lbl">Baseline FRP</div><div class="val">{baseline:.1f} MW</div></div>', unsafe_allow_html=True)
        wc2.markdown(f'<div class="stat"><div class="lbl">Latest FRP</div><div class="val">{latest:.1f} MW</div></div>', unsafe_allow_html=True)
        wc3.markdown(f'<div class="stat"><div class="lbl">Change</div><div class="val" style="color:{"#e66767" if change_pct>0 else "var(--ink)"}">{arrow} {abs(change_pct):.0f}%</div></div>', unsafe_allow_html=True)
        if bool(cluster_row.get("is_anomalous")):
            st.caption(f"Flagged anomalous: latest detection is {zscore:.1f} standard deviations above this "
                       f"cell's own historical baseline (needs ≥{2.0:.0f}σ and ≥{2.0:.0f}× baseline FRP — "
                       "both an operational prototype threshold, not a scientific standard).")
        else:
            st.caption("Within this cell's own normal historical range — not flagged as anomalous.")
    else:
        st.caption("**What Changed?** — not enough detection history at this location yet to establish a baseline.")

    if not detail_rows.empty:
        st.markdown("**Historical Activity**")
        hist = detail_rows.sort_values("acq_date")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=hist["acq_date"], y=hist["frp"], mode="lines+markers",
                                  line=dict(color=color, width=2), marker=dict(size=6), name="FRP (MW)"))
        fig.update_layout(height=220, margin=dict(l=10, r=10, t=10, b=10), template="plotly_dark",
                           paper_bgcolor="#131415", plot_bgcolor="#131415",
                           xaxis=dict(gridcolor="#232320"), yaxis=dict(gridcolor="#232320", title="FRP (MW)"))
        st.plotly_chart(fig, width="stretch")

        st.markdown("**Recent Observations**")
        st.dataframe(
            hist[["acq_date", "frp", "confidence_numeric", "satellite", "daynight"]].sort_values("acq_date", ascending=False).head(10),
            width="stretch", hide_index=True,
        )

    if analyst_mode:
        with st.expander("Analyst view — raw feature values"):
            feature_cols = ["frp", "brightness", "confidence_numeric", "persistence_days", "detection_count",
                             "avg_frp", "max_frp", "frp_trend", "industrial_distance_km", "mine_distance_km",
                             "recurrence_frequency"]
            present = [c for c in feature_cols if c in detail_rows.columns]
            st.dataframe(detail_rows[present].tail(1), width="stretch", hide_index=True)
            st.caption(f"grid_cell={cluster_row['grid_cell']} · zone_type={cluster_row.get('zone_type')}")

    existing_review = store.load_reviews(region="jharkhand_odisha")
    existing_review = existing_review[existing_review["event_id"] == event_id] if not existing_review.empty else existing_review
    b1, b2, b3 = st.columns(3)
    if b1.button("Mark Reviewed", key=f"review_btn_{cluster_row['grid_cell']}", width="stretch"):
        store.save_review(event_id, cluster_row["grid_cell"], "jharkhand_odisha", "Reviewed")
        st.toast("Marked reviewed.", icon=":material/check_circle:")
        st.rerun()
    if not existing_review.empty:
        b1.caption(f"✓ {existing_review.iloc[0]['decision']}")
    if b2.button("View Evidence", key=f"evidence_btn_{cluster_row['grid_cell']}", width="stretch"):
        st.info("Satellite Evidence Preview — DEMO IMAGE, not live satellite imagery. Real imagery integration is a future improvement (see README).", icon=":material/info:")
        st.caption(f"Source: FIRMS thermal detection · Date: {cluster_row['last_detected']} · "
                   f"Coordinates: {cluster_row['latitude']:.4f}, {cluster_row['longitude']:.4f} · Resolution: ~375m (VIIRS) / ~1km (MODIS)")
    b3.button("3D Holo Globe", key=f"inv_jump_3d_{cluster_row['grid_cell']}", width="stretch", icon=":material/public:",
              help="Inspect this thermal event on the interactive 3D Holo Globe",
              on_click=_navigate(page="3D Holo Globe"))


    r1, r2 = st.columns(2)
    report_text = _build_incident_report(cluster_row, detail_rows)
    r1.download_button("Report (Text)", report_text, f"incident_{cluster_row['grid_cell']}.txt", "text/plain",
                        key=f"report_btn_{cluster_row['grid_cell']}", width="stretch")
    report_html = _build_incident_report_html(cluster_row, detail_rows)
    r2.download_button("Report (HTML — print to PDF)", report_html, f"incident_{cluster_row['grid_cell']}.html",
                        "text/html", key=f"report_html_btn_{cluster_row['grid_cell']}", width="stretch")


def _build_incident_report(cluster_row: pd.Series, detail_rows: pd.DataFrame) -> str:
    window_col = f"persistence_{config.PERSISTENCE_DEFAULT_WINDOW_DAYS}d"
    lines = [
        "INCIDENT REPORT — AI-Assisted Early-Warning Platform (SIH26162)",
        "This is a prototype early-warning tool. Satellite detection is NOT ground truth.",
        "=" * 60,
        f"Event ID: {cluster_row.get('event_id', cluster_row['grid_cell'])}",
        f"Grid Cell: {cluster_row['grid_cell']}",
        f"Coordinates: {cluster_row['latitude']:.5f}, {cluster_row['longitude']:.5f}",
        f"Classification: {cluster_row.get('dominant_label')}",
        f"Risk Score: {cluster_row.get('risk_score')}/100 ({cluster_row.get('risk_level')})",
        f"Status: {cluster_row.get('status')}",
        f"Persistence ({config.PERSISTENCE_DEFAULT_WINDOW_DAYS}d window): {cluster_row.get(window_col)} days",
        f"Detection Count: {cluster_row.get('detection_count')}",
        f"Average FRP: {cluster_row.get('avg_frp'):.2f} MW  |  Maximum FRP: {cluster_row.get('max_frp'):.2f} MW",
        f"Industrial Context: zone_type={cluster_row.get('zone_type')}, zone_kind={cluster_row.get('zone_kind', '?')}, "
        f"distance={cluster_row.get('industrial_distance_km')} km",
        f"First Detected: {cluster_row.get('first_detected')}  |  Last Detected: {cluster_row.get('last_detected')}",
    ]
    if bool(cluster_row.get("has_baseline")):
        lines.append(
            f"What Changed: baseline {cluster_row.get('frp_baseline_mean', 0):.1f} MW -> latest "
            f"{cluster_row.get('latest_frp', 0):.1f} MW ({cluster_row.get('frp_change_pct', 0):+.0f}%) — "
            f"{'ANOMALOUS' if cluster_row.get('is_anomalous') else 'within normal range'}"
        )
    lines += [
        "-" * 60,
        "AI Explanation:",
    ]
    if not detail_rows.empty:
        for item in str(detail_rows.iloc[-1].get("rule_evidence", "")).split("|"):
            if item.strip():
                lines.append(f"  - {item}")
    lines += [
        "-" * 60,
        "Data Sources: NASA FIRMS (thermal hotspots), OpenStreetMap (industrial/mining context)",
        f"Generated: {pd.Timestamp.now().isoformat()}",
    ]
    return "\n".join(lines)


def _build_incident_report_html(cluster_row: pd.Series, detail_rows: pd.DataFrame) -> str:
    """A styled, standalone HTML report — no external assets, so it opens
    correctly offline and can be turned into a PDF via the browser's own
    Print dialog without adding a PDF-generation dependency to the project."""
    window_col = f"persistence_{config.PERSISTENCE_DEFAULT_WINDOW_DAYS}d"
    label = cluster_row.get("dominant_label", "Requires Verification")
    color = CATEGORY_COLORS.get(label, "#888888")
    risk_lvl = cluster_row.get("risk_level", "LOW")

    def _row(k, v):
        return f'<tr><td class="k">{k}</td><td class="v">{v}</td></tr>'

    rows = [
        _row("Event ID", cluster_row.get("event_id", cluster_row["grid_cell"])),
        _row("Grid Cell", cluster_row["grid_cell"]),
        _row("Coordinates", f"{cluster_row['latitude']:.5f}, {cluster_row['longitude']:.5f}"),
        _row("Status", cluster_row.get("status", "?")),
        _row("Persistence", f"{cluster_row.get(window_col, 0)} of {config.PERSISTENCE_DEFAULT_WINDOW_DAYS} days"),
        _row("Detection Count", int(cluster_row.get("detection_count", 0))),
        _row("Average / Maximum FRP", f"{cluster_row.get('avg_frp', 0):.2f} MW / {cluster_row.get('max_frp', 0):.2f} MW"),
        _row("Zone Type / Kind", f"{cluster_row.get('zone_type', '?')} / {cluster_row.get('zone_kind', '?')}"),
        _row("Industrial / Mine / Power Distance",
             f"{cluster_row.get('industrial_distance_km', float('nan')):.2f} km / "
             f"{cluster_row.get('mine_distance_km', float('nan')):.2f} km / "
             f"{cluster_row.get('power_distance_km', float('nan')):.2f} km"),
        _row("First / Last Detected", f"{cluster_row.get('first_detected')} / {cluster_row.get('last_detected')}"),
    ]
    if bool(cluster_row.get("has_baseline")):
        anomaly_html = '<b style="color:#e66767">ANOMALOUS</b>' if cluster_row.get("is_anomalous") else "within normal range"
        rows.append(_row(
            "What Changed",
            f"{cluster_row.get('frp_baseline_mean', 0):.1f} MW &rarr; {cluster_row.get('latest_frp', 0):.1f} MW "
            f"({cluster_row.get('frp_change_pct', 0):+.0f}%) — {anomaly_html}"
        ))

    evidence_items = ""
    if not detail_rows.empty:
        for item in str(detail_rows.iloc[-1].get("rule_evidence", "")).split("|"):
            if item.strip():
                evidence_items += f"<li>{item.strip()}</li>"

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Incident Report — {cluster_row.get('event_id', cluster_row['grid_cell'])}</title>
<style>
body{{font-family:'IBM Plex Sans',system-ui,-apple-system,'Segoe UI',sans-serif;background:#0c0d0e;color:#e8e9ea;
  max-width:720px;margin:2rem auto;padding:0 1.5rem;}}
h1{{font-size:1.3rem;margin-bottom:.1rem;}}
.eyebrow{{font-family:monospace;font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;color:#4d8fc4;}}
.disclaimer{{font-size:.82rem;color:#9a9da1;border-left:3px solid #4d8fc4;padding:.4rem .8rem;margin:1rem 0;background:#131415;}}
.pill{{display:inline-block;font-family:monospace;font-size:.75rem;font-weight:600;padding:.2rem .6rem;border-radius:99px;
  color:{color};background:{color}22;border:1px solid {color}55;margin-right:.4rem;}}
table{{width:100%;border-collapse:collapse;margin:1rem 0;font-size:.85rem;}}
td{{padding:.4rem .6rem;border-bottom:1px solid rgba(255,255,255,.08);}}
td.k{{color:#9a9da1;width:40%;}}
td.v{{font-family:monospace;}}
h2{{font-size:.95rem;border-bottom:1px solid rgba(255,255,255,.16);padding-bottom:.3rem;margin-top:1.5rem;}}
ul{{font-size:.85rem;line-height:1.7;}}
.footer{{font-size:.72rem;color:#6b6e72;margin-top:2rem;border-top:1px dashed rgba(255,255,255,.08);padding-top:.6rem;}}
@media print{{body{{background:#fff;color:#111;}} .disclaimer{{background:#f4f4f4;}} td{{border-color:#ddd;}}}}
</style></head>
<body>
<div class="eyebrow">SIH26162 &middot; AI-Assisted Early-Warning Platform</div>
<h1>Incident Report</h1>
<div class="disclaimer">This is a prototype early-warning tool. Satellite detection is an observation, NOT ground-confirmed fire certification. See the Methodology &amp; Limitations section of the dashboard before acting on this report.</div>
<span class="pill">{label}</span>
<span class="pill">RISK {cluster_row.get('risk_score', 0):.0f}/100 ({risk_lvl})</span>
<table>{"".join(rows)}</table>
<h2>AI Explanation</h2>
<ul>{evidence_items or "<li>No evidence recorded.</li>"}</ul>
<div class="footer">
Data Sources: NASA FIRMS (thermal hotspots), OpenStreetMap (industrial/mining context)<br>
Generated: {pd.Timestamp.now().isoformat()}
</div>
</body></html>"""


# ------------------------------------------------------------------ nav --

NAV_PAGES = ["Overview", "Live Map", "3D Holo Globe", "Events", "Alerts", "Analytics",
             "Investigations", "Validation", "AI Model", "Data", "Settings"]
NAV_ICONS = {
    "Overview": "space_dashboard", "Live Map": "map", "3D Holo Globe": "public",
    "Events": "flare", "Alerts": "notifications_active", "Analytics": "monitoring",
    "Investigations": "manage_search", "Validation": "fact_check",
    "AI Model": "smart_toy", "Data": "database", "Settings": "settings",
}
PRESENTATION_ALLOWED_PAGES = {"Overview", "Live Map", "3D Holo Globe", "Alerts", "Analytics", "Investigations"}



def _navigate(page: str | None = None, region: str | None = None, selected_cell: str | None = None):
    """Returns an on_click callback that changes page/region/selected_cell.
    Must be wired via `st.button(..., on_click=_navigate(...))`, NOT called
    inside an `if st.button(...):` block — the sidebar nav buttons/topbar_region
    widgets are already instantiated earlier in the same script run (the
    sidebar and top bar render before any page's own content), so setting
    their session_state keys directly at that point raises
    StreamlitAPIException. A callback passed to on_click runs BEFORE the
    next rerun's widgets exist yet, which is the only point such a write is
    allowed."""
    def _cb():
        if selected_cell is not None:
            st.session_state["selected_cell"] = selected_cell
        if page is not None:
            st.session_state["page"] = page
        if region is not None:
            st.session_state["region"] = region
            st.session_state["topbar_region"] = "India" if region == "india" else "Jharkhand–Odisha Belt"
    return _cb


def _render_sidebar_nav() -> str:
    with st.sidebar:
        st.markdown('<div class="brand">THERMAL INTELLIGENCE</div>'
                     '<div class="brand-sub">AI-Assisted Satellite Monitoring</div>', unsafe_allow_html=True)
        st.markdown('<div class="side-label" style="margin-top:.9rem;">Navigation</div>', unsafe_allow_html=True)
        page = st.session_state.get("page", "Overview")
        for p in NAV_PAGES:
            st.button(
                p, key=f"navbtn_{p}", icon=f":material/{NAV_ICONS[p]}:",
                type="primary" if p == page else "secondary",
                width="stretch", on_click=_navigate(page=p),
            )

        st.divider()
        st.markdown('<div class="side-label">System</div>', unsafe_allow_html=True)
        demo_mode = st.toggle("Demo Mode", value=st.session_state["demo_mode"], key="demo_mode_toggle",
                               help="Use the fixed local demo dataset — never depends on external APIs.")
        st.session_state["demo_mode"] = demo_mode
        if demo_mode:
            st.markdown('<span class="badge-demo">DEMO MODE ACTIVE</span>', unsafe_allow_html=True)
        st.caption("Pipeline run, API key, and threshold controls live on the **Settings** page.")
    return page


def _derive_national_alerts(events_df: pd.DataFrame) -> list[dict]:
    """No national alert-engine run exists (no rule-based classification runs
    country-wide) — these are computed on the fly from real classified event
    rows, not a separate stored/fabricated alert feed."""
    if events_df is None or events_df.empty:
        return []
    sev = events_df[events_df["risk_level"].isin(["HIGH", "CRITICAL"])].sort_values("risk_score", ascending=False)
    alerts = []
    for _, r in sev.iterrows():
        alerts.append({
            "title": f"{r.get('risk_level')} thermal activity — {r.get('state') or 'Unknown state'}",
            "event_id": r.get("event_id", r.get("grid_cell")), "grid_cell": r.get("grid_cell"),
            "latitude": r.get("latitude", 0.0), "longitude": r.get("longitude", 0.0),
            "classification": "Persistent Source" if r.get("is_persistent") else "Thermal Event",
            "risk_score": r.get("risk_score", 0), "persistence_days": r.get("persistence_days", 0),
            "frp": r.get("avg_frp", 0.0), "status": r.get("risk_level"), "severity": r.get("risk_level"),
        })
    return alerts


def _handle_global_search(query: str, region: str):
    query_norm = query.strip().lower()
    if not query_norm:
        return
    if region == "jharkhand_odisha":
        cluster_df = _load_cached_clusters()
        if cluster_df.empty:
            st.caption("No data loaded yet.")
            return
        matches = cluster_df[cluster_df["grid_cell"].str.lower().str.contains(query_norm, na=False)]
        if matches.empty:
            st.caption(f"No match for '{query}'.")
        else:
            cell = matches.iloc[0]["grid_cell"]
            st.button(f"Open {cell}", key="search_jump_belt", icon=":material/manage_search:",
                      on_click=_navigate(page="Investigations", selected_cell=cell))
    else:
        info = st.session_state.get("national_info")
        if not info or info["events_df"].empty:
            st.caption("No data loaded yet.")
            return
        ev = info["events_df"]
        matches = ev[ev.apply(lambda r: query_norm in str(r.get("grid_cell", "")).lower()
                               or query_norm in str(r.get("state", "")).lower(), axis=1)]
        st.caption(f"{len(matches)} match(es) — refine on the Events page." if not matches.empty else f"No match for '{query}'.")


def _render_topbar():
    region = st.session_state["region"]
    demo_mode = st.session_state["demo_mode"]

    if region == "india":
        info = st.session_state.get("national_info")
        has_run = bool(info)
        src = "DEMO DATA" if demo_mode else ((info or {}).get("hotspot_source", "NOT YET RUN").upper().replace("_", " "))
        dot = "demo" if demo_mode else ("live" if (info or {}).get("hotspot_source") == "firms_live" else "stale")
        alerts = _derive_national_alerts(info["events_df"]) if info else []
    else:
        run_info = st.session_state.get("run_info")
        has_run = bool(run_info)
        src = "DEMO DATA" if demo_mode else ((run_info or {}).get("hotspot_source", "NOT YET RUN").upper().replace("_", " "))
        dot = "demo" if demo_mode else ("live" if (run_info or {}).get("hotspot_source") == "firms_live" else "stale")
        alerts = _load_cached_alerts()

    n_critical = sum(1 for a in alerts if a.get("severity") == "CRITICAL")
    updated = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M") if has_run else "never run"

    c1, c2, c3, c4, c5 = st.columns([3.2, 1.3, 1.3, 2.2, 1.1])
    with c1:
        st.markdown(
            '<div class="topbar-brand"><div class="eyebrow">SIH26162 &middot; Ministry: NTRO</div>'
            '<h1>THERMAL INTELLIGENCE</h1>'
            '<p class="sub">AI-assisted satellite monitoring &amp; industrial thermal risk analysis.</p></div>',
            unsafe_allow_html=True,
        )
    with c2:
        # Same rationale as nav_radio above: no `index=` once topbar_region
        # can also be set programmatically via a callback (_navigate).
        st.session_state.setdefault("topbar_region", "India" if region == "india" else "Jharkhand–Odisha Belt")
        region_label = st.selectbox("Region", ["India", "Jharkhand–Odisha Belt"], key="topbar_region")
        new_region = "india" if region_label == "India" else "jharkhand_odisha"
        if new_region != region:
            st.session_state["region"] = new_region
            st.rerun()
    with c3:
        st.markdown(f'<div class="topbar-meta"><span class="dot {dot}"></span>{src}<br>Updated: {updated}</div>',
                     unsafe_allow_html=True)
    with c4:
        query = st.text_input("Search", placeholder="Search event ID, location, coordinates...",
                               label_visibility="collapsed", key="global_search")
        if query:
            _handle_global_search(query, region)
    with c5:
        st.button(f"Alerts ({n_critical})", key="topbar_alerts_btn", width="stretch",
                  icon=":material/notifications_active:", on_click=_navigate(page="Alerts"))
        st.caption("Analyst · Administrator")
    st.markdown('<hr class="topbar-rule">', unsafe_allow_html=True)


def _render_methodology_expander():
    with st.expander("Methodology & Limitations"):
        st.markdown(
            "- Satellite detections are observations, not ground confirmation — a hotspot is a thermal "
            "anomaly the sensor registered, not a verified fire.\n"
            "- Small or low-intensity fires may be missed entirely.\n"
            "- Cloud cover and smoke reduce detection probability; **absence of a detection during a period "
            "should not be interpreted as absence of thermal activity.**\n"
            "- Satellite spatial resolution (~375m VIIRS, ~1km MODIS) limits positional precision — a hotspot "
            "coordinate is the detected pixel's location, not necessarily the exact fire location.\n"
            "- Persistent industrial thermal sources may reflect normal operations, not an emergency.\n"
            "- OpenStreetMap coverage may be incomplete in some areas, affecting industrial-zone tagging.\n"
            "- AI classifications are prototype outputs that require human validation before acting on them.\n"
            "- The risk score is an operational prototype metric, not an official government fire-risk standard."
        )


# ------------------------------------------------------------------ main --

def main():
    st.session_state.setdefault("demo_mode", not bool(config.FIRMS_API_KEY))
    st.session_state.setdefault("analyst_mode", False)
    st.session_state.setdefault("selected_cell", None)
    st.session_state.setdefault("region", config.DEFAULT_REGION)
    st.session_state.setdefault("presentation_mode", False)
    st.session_state.setdefault("page", "Overview")
    st.session_state.setdefault("alert_phone", config.ALERT_RECIPIENT_PHONE)
    st.session_state.setdefault("alert_auto_dispatch", config.ALERT_AUTO_DISPATCH_CRITICAL)

    st.markdown(CSS, unsafe_allow_html=True)

    _render_sidebar_nav()
    _render_topbar()

    region = st.session_state["region"]
    demo_mode = st.session_state["demo_mode"]
    page = st.session_state["page"]

    if st.session_state["presentation_mode"] and page not in PRESENTATION_ALLOWED_PAGES:
        st.info("This page is hidden in **Presentation Mode**. Turn it off on the Settings page to reach "
                "technical/admin pages during setup.", icon=":material/info:")
        return

    if region == "india":
        _route_national_page(page, demo_mode)
    else:
        _route_regional_page(page, demo_mode)


# ----------------------------------------------------- regional (belt) routing --

# Pages that are allowed to render the Filters panel. Every other page reuses
# whatever the analyst last selected here (or the defaults) without showing the UI.
FILTER_PAGES = ("Live Map",)


def _apply_regional_filters(gdf: gpd.GeoDataFrame, cluster_df: pd.DataFrame, page: str):
    show_ui = page in FILTER_PAGES
    min_date, max_date = gdf["acq_date"].min().date(), gdf["acq_date"].max().date()
    frp_max_val = float(gdf["frp"].max()) if not gdf.empty else 50.0

    # Shared (page-independent) widget keys so filters set on the Live Map page
    # stay applied when the analyst moves to other pages.
    defaults = {
        "flt_date": (min_date, max_date),
        "flt_cls": list(CATEGORY_COLORS.keys()),
        "flt_risk": list(RISK_COLORS.keys()),
        "flt_label": "rule_label",
        "flt_conf": 0,
        "flt_pers": 0,
        "flt_frp": (0.0, max(frp_max_val, 1.0)),
        "flt_color": "classification",
        "flt_onlyp": False,
        "flt_onlyc": False,
    }

    if show_ui:
        with st.container(border=True):
            _section_header("Filters", icon="tune")
            f1, f2, f3, f4 = st.columns(4)
            date_range = f1.slider("Date Range", min_value=min_date, max_value=max_date,
                                    value=(min_date, max_date), key="flt_date") if min_date != max_date else (min_date, max_date)
            classifications = f2.multiselect("Classification", list(CATEGORY_COLORS.keys()),
                                              default=list(CATEGORY_COLORS.keys()), key="flt_cls")
            risk_levels = f3.multiselect("Risk Level", list(RISK_COLORS.keys()),
                                          default=list(RISK_COLORS.keys()), key="flt_risk")
            label_field = f4.radio("Label Source", ["rule_label", "ml_label"], horizontal=True, key="flt_label")

            g1, g2, g3, g4 = st.columns(4)
            min_conf = g1.slider("Min Confidence", 0, 100, 0, key="flt_conf")
            min_persist = g2.slider("Min Persistence (days)", 0, int(gdf["persistence_days"].max()) or 1, 0, key="flt_pers")
            frp_range = g3.slider("FRP Range (MW)", 0.0, max(frp_max_val, 1.0), (0.0, max(frp_max_val, 1.0)), key="flt_frp")
            color_by = g4.radio("Map Color By", ["classification", "risk"], horizontal=True, key="flt_color")

            h1, h2, h3 = st.columns([1, 1, 2])
            only_persistent = h1.checkbox("Only Persistent", key="flt_onlyp")
            only_critical = h2.checkbox("Only Critical Risk", key="flt_onlyc")
            if h3.button("Reset Filters", key="flt_reset"):
                for k in defaults:
                    st.session_state.pop(k, None)
                st.rerun()
    else:
        # No filter UI on this page — fall back to the last values chosen on the
        # Live Map page, or to the wide-open defaults.
        get = lambda k: st.session_state.get(k, defaults[k])
        date_range = get("flt_date")
        classifications, risk_levels = get("flt_cls"), get("flt_risk")
        min_conf, min_persist, frp_range = get("flt_conf"), get("flt_pers"), get("flt_frp")
        only_persistent, only_critical = get("flt_onlyp"), get("flt_onlyc")
        label_field, color_by = get("flt_label"), get("flt_color")
        # Guard against stale ranges after the dataset window changes.
        date_range = (max(date_range[0], min_date), min(date_range[1], max_date))
        frp_range = (frp_range[0], min(frp_range[1], max(frp_max_val, 1.0)))

    mask = (
        (gdf["acq_date"].dt.date >= date_range[0]) & (gdf["acq_date"].dt.date <= date_range[1])
        & (gdf["confidence_numeric"] >= min_conf) & (gdf[label_field].isin(classifications))
        & (gdf["risk_level"].isin(risk_levels)) & (gdf["persistence_days"] >= min_persist)
        & (gdf["frp"].between(frp_range[0], frp_range[1]))
    )
    if only_persistent:
        mask &= gdf["is_persistent"].astype(bool)
    if only_critical:
        mask &= gdf["risk_level"] == "CRITICAL"
    filtered = gdf[mask]
    filtered_cells = set(filtered["grid_cell"]) if not filtered.empty else set()
    filtered_clusters = cluster_df[cluster_df["grid_cell"].isin(filtered_cells)] if not cluster_df.empty else cluster_df
    return filtered, filtered_clusters, label_field, color_by


def _render_events_table(df: pd.DataFrame, region_key: str):
    with st.container(border=True):
        _section_header(f"Events — {len(df)} rows", icon="flare")
        if df.empty:
            st.info("No events match the current filters.", icon=":material/search_off:")
            return
        search = st.text_input("Search grid cell / state / classification", key=f"events_search_{region_key}")
        table = df.copy()
        if search:
            m = table.astype(str).apply(lambda col: col.str.contains(search, case=False, na=False)).any(axis=1)
            table = table[m]
        st.dataframe(table, hide_index=True, width="stretch")
        st.download_button("Export CSV", table.to_csv(index=False), f"events_{region_key}.csv", "text/csv",
                            key=f"events_export_{region_key}")


def _render_validation_belt(filtered: pd.DataFrame):
    if filtered is None or filtered.empty:
        st.info("No data in the current filter selection.", icon=":material/search_off:")
        return
    pending = filtered[filtered["rule_label"] == "Requires Verification"].drop_duplicates("grid_cell")
    reviews = store.load_reviews(region="jharkhand_odisha").set_index("event_id")
    reviewed_n = sum(1 for _, r in pending.iterrows() if event_id_for_cell(r["grid_cell"]) in reviews.index)
    _section_header(f"Validation Queue — {reviewed_n} / {len(pending)} reviewed", icon="fact_check")
    st.caption("Analyst decisions below are written to a persistent SQLite audit trail "
               "(`analyst_reviews` table) — the latest decision per event, with a timestamp; "
               "not a full multi-review history log.")
    if pending.empty:
        st.caption("Nothing pending review in the current filter selection.")
        return
    for _, r in pending.iterrows():
        cell = r["grid_cell"]
        eid = event_id_for_cell(cell)
        with st.container(border=True):
            c1, c2 = st.columns([3, 1])
            c1.markdown(f"**{eid}** &middot; {r['latitude']:.4f}, {r['longitude']:.4f} &middot; "
                        f"FRP {r['frp']:.1f} MW &middot; Confidence {r['confidence_numeric']:.0f}", unsafe_allow_html=True)
            if eid in reviews.index:
                row = reviews.loc[eid]
                c2.caption(f"✓ {row['decision']} — {str(row['reviewed_at'])[:16]}")
            b1, b2, b3 = st.columns(3)
            if b1.button("Confirm", key=f"val_confirm_{cell}", width="stretch"):
                store.save_review(eid, cell, "jharkhand_odisha", "Confirmed")
                st.toast(f"{eid} marked confirmed.", icon=":material/check_circle:")
                st.rerun()
            if b2.button("Reject", key=f"val_reject_{cell}", width="stretch"):
                store.save_review(eid, cell, "jharkhand_odisha", "Rejected")
                st.toast(f"{eid} marked rejected.", icon=":material/cancel:")
                st.rerun()
            b3.button("Open Investigation", key=f"val_open_{cell}", width="stretch",
                      on_click=_navigate(page="Investigations", selected_cell=cell))


def _render_settings_belt(demo_mode: bool):
    with st.container(border=True):
        _section_header("Pipeline", icon="tune")
        api_key_input = None
        if not demo_mode:
            if config.FIRMS_API_KEY:
                st.success("FIRMS_API_KEY loaded from .env", icon=":material/check_circle:")
            else:
                st.warning("No FIRMS_API_KEY configured — pipeline will fall back to cache/demo data.", icon=":material/warning:")
            api_key_input = st.text_input("Or paste a FIRMS key for this session", type="password", key="settings_belt_key")
            if st.button("Validate Key", key="settings_belt_validate", icon=":material/verified:") and (api_key_input or config.FIRMS_API_KEY):
                try:
                    check_map_key(api_key_input or config.FIRMS_API_KEY)
                    st.success("Key is valid.", icon=":material/check_circle:")
                except FirmsAuthError as exc:
                    st.error(str(exc), icon=":material/cancel:")
        if st.button("Run Pipeline", key="settings_belt_run", width="stretch", icon=":material/play_circle:"):
            run_and_cache(demo_mode, api_key_input or None)
            st.rerun()

    with st.container(border=True):
        _section_header("View", icon="visibility")
        st.session_state["analyst_mode"] = st.toggle("Analyst Mode", value=st.session_state["analyst_mode"], key="analyst_mode_toggle",
                                                       help="Expose raw features, model probabilities, and processing internals.")
        st.session_state["presentation_mode"] = st.toggle("Presentation Mode", value=st.session_state["presentation_mode"],
                                                            key="presentation_mode_toggle_belt",
                                                            help="Hide technical/admin pages for a clean SIH demo view.")

    with st.container(border=True):
        _section_header("Operational Parameters (prototype, not scientific constants)", icon="tune")
        min_days = st.slider("Persistence threshold (days)", 2, 15, config.PERSISTENCE_MIN_DAYS, key="settings_persist_slider")
        st.caption(f"Currently: ≥{min_days} distinct days in {config.PERSISTENCE_DEFAULT_WINDOW_DAYS} ⇒ persistent. "
                   "(Changing this requires re-running the pipeline with an updated threshold — wire-up left for a future iteration.)")

        st.markdown("**Risk Score Weights**")
        st.caption("Adjust and click Recompute to re-score the currently loaded data with these weights — "
                   "no re-fetch/re-classification needed, only the risk score, status, and alerts are recalculated.")
        w1, w2, w3 = st.columns(3)
        w_persistence = w1.slider("Persistence", 0.0, 1.0, config.RISK_WEIGHTS["persistence"], 0.05, key="w_persistence")
        w_frp = w2.slider("FRP", 0.0, 1.0, config.RISK_WEIGHTS["frp"], 0.05, key="w_frp")
        w_confidence = w3.slider("Confidence", 0.0, 1.0, config.RISK_WEIGHTS["confidence"], 0.05, key="w_confidence")
        w4, w5, _ = st.columns(3)
        w_industrial = w4.slider("Industrial Proximity", 0.0, 1.0, config.RISK_WEIGHTS["industrial_proximity"], 0.05, key="w_industrial")
        w_recurrence = w5.slider("Recurrence", 0.0, 1.0, config.RISK_WEIGHTS["recurrence"], 0.05, key="w_recurrence")
        weight_total = w_persistence + w_frp + w_confidence + w_industrial + w_recurrence
        st.caption(f"Weights sum to {weight_total:.2f} (need not be exactly 1.00 — each component score is already "
                   "0-100, and the total is clamped to 0-100 either way).")
        if st.button("Recompute Risk Scores", key="recompute_risk_btn", width="stretch", icon=":material/calculate:"):
            custom_weights = {"persistence": w_persistence, "frp": w_frp, "confidence": w_confidence,
                               "industrial_proximity": w_industrial, "recurrence": w_recurrence}
            recompute_risk_and_cache(custom_weights)
            st.rerun()

    with st.container(border=True):
        _section_header("Critical Alert SMS & Messaging Gateway", icon="sms", icon_color="var(--accent-critical)")
        st.caption("Automated and manual high-priority text alert dispatch to field responders for CRITICAL thermal events.")

        msg1, msg2 = st.columns(2)
        with msg1:
            alert_phone_val = st.text_input(
                "Recipient Phone Number (SMS)",
                value=st.session_state.get("alert_phone", config.ALERT_RECIPIENT_PHONE),
                key="alert_settings_phone",
                help="Target mobile number for automated critical alerts (+country code or 10 digits).",
            )
            st.session_state["alert_phone"] = alert_phone_val
        with msg2:
            alert_auto = st.toggle(
                "Auto-notify on Critical Alerts (Severity = CRITICAL)",
                value=st.session_state.get("alert_auto_dispatch", config.ALERT_AUTO_DISPATCH_CRITICAL),
                key="alert_settings_auto",
                help="Automatically dispatch SMS/messages whenever critical thermal events (Risk >= 76 or CRITICAL severity) are detected.",
            )
            st.session_state["alert_auto_dispatch"] = alert_auto

        with st.expander("Twilio SMS & Messaging Channel Credentials", expanded=False):
            st.caption("Optional credentials for live Twilio SMS, Telegram, and Webhook. If left unconfigured, alerts are safely simulated and recorded to the local audit log.")
            t_sid = st.text_input("Twilio Account SID", value=config.TWILIO_ACCOUNT_SID, type="password", key="msg_t_sid")
            t_tok = st.text_input("Twilio Auth Token", value=config.TWILIO_AUTH_TOKEN, type="password", key="msg_t_tok")
            t_from = st.text_input("Twilio From Phone Number", value=config.TWILIO_FROM_NUMBER, key="msg_t_from")
            tg_tok = st.text_input("Telegram Bot Token", value=config.TELEGRAM_BOT_TOKEN, type="password", key="msg_tg_tok")
            tg_cid = st.text_input("Telegram Chat ID", value=config.TELEGRAM_CHAT_ID, key="msg_tg_cid")
            wb_url = st.text_input("Custom Webhook URL", value=config.ALERT_WEBHOOK_URL, key="msg_wb_url")

        send_phone = alert_phone_val or config.ALERT_RECIPIENT_PHONE
        if st.button("Send Test Critical Alert Message to " + send_phone, key="msg_settings_send_test", width="stretch", icon=":material/sms:"):
            from src.alerts import messages as alert_messages
            sample_event = {
                "event_id": "TH-TEST-CRIT",
                "latitude": 22.8046, "longitude": 86.1850,
                "risk_score": 88.5, "risk_level": "CRITICAL",
                "severity": "CRITICAL",
                "classification": "Likely Industrial Fire",
                "ai_confidence": 94.2, "frp": 16.5, "persistence_days": 24,
                "industrial_distance_km": 0.15, "status": "Requires immediate verification.",
            }
            res = alert_messages.send_critical_alert(
                sample_event,
                phone=send_phone,
                force=True,
                twilio_sid=t_sid or None,
                twilio_token=t_tok or None,
                twilio_from=t_from or None,
                telegram_token=tg_tok or None,
                telegram_chat_id=tg_cid or None,
                webhook_url=wb_url or None,
            )
            if res["status"] in ("delivered", "simulated"):
                st.success(f"Critical alert message dispatched successfully to {send_phone} ({res['detail']})!", icon=":material/check_circle:")
                st.toast(f"Dispatched to {send_phone}", icon=":material/sms:")
            else:
                st.error(f"Dispatch failed: {res.get('detail', 'Unknown error')}", icon=":material/cancel:")

    with st.container(border=True):
        _section_header("3D Holo Globe & Digital Twin Integration", icon="public")
        st.caption("Real-time synchronization between the Python intelligence pipeline and the Holo-View-Maker 3D WebGL Globe.")

        holo_host_belt = st.text_input(
            "Holo-View App URL / Port",
            value=st.session_state.get("holo_host_url", "http://localhost:5173"),
            key="settings_holo_url_belt",
            help="Local or remote URL where the Holo-View-Maker React/Three.js application is running.",
        )
        st.session_state["holo_host_url"] = holo_host_belt

        c1, c2 = st.columns(2)
        with c1:
            events_synced = st.session_state.get("holo_events_count", len(load_or_export_holo_events()))
            st.markdown(
                f'<div style="font-size:0.83rem;color:var(--ink);line-height:1.6;">'
                f'<b>Sync Status:</b> <span class="mono" style="color:#0ca30c;">● ACTIVE</span> &middot; '
                f'<b>Synced Events:</b> <span class="mono">{events_synced}</span><br>'
                f'<b>Last Synced:</b> <span class="mono">{st.session_state.get("holo_last_synced", "Active session")}</span><br>'
                f'<span style="font-size:0.75rem;color:var(--ink2);">Destination: <code>holo-view-maker/public/data/events.json</code></span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        with c2:
            if st.button("Sync Current Pipeline to 3D Globe Now", key="sync_holo_settings_belt", width="stretch", icon=":material/sync:"):
                with st.spinner("Exporting thermal events to 3D Holo Globe..."):
                    gdf_curr = _load_cached_detail()
                    c_df_curr = _load_cached_clusters()
                    exported_3d = export_pipeline_events_for_holo_view(gdf_curr, c_df_curr)
                    st.session_state["holo_events_count"] = len(exported_3d)
                    st.session_state["holo_last_synced"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
                    st.toast(f"Synced {len(exported_3d)} events to 3D Holo Globe!", icon=":material/public:")
                    st.success(f"Successfully exported {len(exported_3d)} events to Holo-View 3D Globe!", icon=":material/check_circle:")


def _route_regional_page(page: str, demo_mode: bool):
    gdf = _load_cached_detail()
    cluster_df = _load_cached_clusters()
    alerts = _load_cached_alerts()
    run_info = st.session_state.get("run_info")

    if page == "Settings":
        _render_settings_belt(demo_mode)
        return

    if gdf is None or gdf.empty:
        st.info("No classified data yet for the Jharkhand–Odisha belt. Open **Settings** and click "
                "**Run Pipeline** (Demo Mode works with zero setup).", icon=":material/info:")
        return

    filtered, filtered_clusters, label_field, color_by = _apply_regional_filters(gdf, cluster_df, page)

    if page == "Overview":
        _render_kpis(gdf, cluster_df, alerts)
        _render_alert_banner(alerts)
        _render_overview(filtered, filtered_clusters, label_field, color_by)
        _render_methodology_expander()
    elif page == "Live Map":
        _render_live_map(filtered, label_field, color_by)
    elif page == "3D Holo Globe":
        _render_3d_globe_page(filtered, filtered_clusters, is_regional=True)
    elif page == "Events":
        _render_events_table(filtered_clusters, "belt")
    elif page == "Alerts":
        _render_alerts_tab(alerts)
    elif page == "Analytics":
        _render_analytics(filtered, filtered_clusters, run_info)
    elif page == "Investigations":
        _render_investigations(filtered_clusters, filtered, st.session_state["analyst_mode"])
    elif page == "Validation":
        _render_validation_belt(filtered)
    elif page == "AI Model":
        _render_model_tab(run_info)
    elif page == "Data":
        _render_data_tab(filtered, run_info)
        _render_methodology_expander()



def _render_kpis(gdf, cluster_df, alerts):
    # Observation -> Event -> Persistent Source funnel discipline (see
    # Methodology): event-level counts come from cluster_df (one row per
    # ~1km grid cell) so a single recurring source isn't recounted once per
    # daily detection the way a raw gdf-row sum would.
    n_total = len(gdf)
    n_events = int(cluster_df["grid_cell"].nunique()) if not cluster_df.empty else 0
    n_persistent = int(cluster_df["is_persistent"].sum()) if not cluster_df.empty and "is_persistent" in cluster_df else 0
    n_industrial_fire = int((cluster_df["dominant_label"] == "Likely Industrial Fire").sum()) if not cluster_df.empty and "dominant_label" in cluster_df else 0
    n_high_risk = int((cluster_df["risk_level"] == "HIGH").sum()) if not cluster_df.empty and "risk_level" in cluster_df else 0
    n_critical = int((cluster_df["risk_level"] == "CRITICAL").sum()) if not cluster_df.empty and "risk_level" in cluster_df else 0
    today = gdf["acq_date"].max()
    n_new_today = int((gdf["acq_date"] == today).sum())
    n_review = int((cluster_df["dominant_label"] == "Requires Verification").sum()) if not cluster_df.empty and "dominant_label" in cluster_df else 0

    _stat_row([
        ("Satellite Observations", n_total, False, "satellite_alt", None),
        ("Thermal Events", n_events, False, "flare", None),
        ("Persistent Sources", n_persistent, n_persistent > 0, "schedule", STATUS_COLORS["PERSISTENT"] if n_persistent else None),
        ("High-Risk Events", n_high_risk, n_high_risk > 0, "warning", RISK_COLORS["HIGH"] if n_high_risk else None),
    ])
    _stat_row([
        ("Critical Alerts", sum(1 for a in alerts if a.get("severity") == "CRITICAL"), n_critical > 0, "warning", RISK_COLORS["CRITICAL"] if n_critical else None),
        ("Industrial Fires", n_industrial_fire, n_industrial_fire > 0, "local_fire_department", CATEGORY_COLORS["Likely Industrial Fire"] if n_industrial_fire else None),
        ("New Today", n_new_today, False, "today", None),
        ("Requires Review", n_review, False, "fact_check", None),
    ])


def _render_alert_banner(alerts):
    if not alerts:
        return
    n_critical = sum(1 for a in alerts if a.get("severity") == "CRITICAL")
    n_high = sum(1 for a in alerts if a.get("severity") == "HIGH")
    if n_critical == 0 and n_high == 0:
        return
    st.markdown(
        f'<div class="alertbar"><span class="txt">:material/warning: <b>{n_critical}</b> critical and <b>{n_high}</b> '
        f'high-priority thermal events require review.</span></div>',
        unsafe_allow_html=True,
    )


def _render_overview(filtered, filtered_clusters, label_field, color_by):
    with st.container(border=True):
        r1, r2, r3, r4 = st.columns([2.5, 1.3, 1.3, 1.1])
        with r1:
            _section_header("Regional Operations — Jharkhand–Odisha Belt", icon="space_dashboard")
            st.caption(":material/location_on: Real-time AI satellite thermal intelligence, persistence tracking, and industrial hotspot monitoring.")
        with r2:
            st.button("Open Live Map", key="overview_open_live_map", width="stretch", icon=":material/map:",
                      help="Explore interactive 2D GIS map with clustering, satellite imagery, and zone boundaries",
                      on_click=_navigate(page="Live Map"))
        with r3:
            st.button("3D Holo Globe", key="overview_open_3d_globe", width="stretch", icon=":material/public:",
                      help="Explore these thermal events in the interactive 3D Holo Globe",
                      on_click=_navigate(page="3D Holo Globe"))
        with r4:
            st.button("India View", key="back_india_overview", width="stretch", icon=":material/arrow_back:",
                      on_click=_navigate(page="Overview", region="india"))

    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            _section_header("Trend (Daily Detections)", icon="show_chart")
            if not filtered.empty:
                daily = filtered.groupby([filtered["acq_date"].dt.date, label_field]).size().unstack(fill_value=0)
                st.line_chart(daily)
    with c2:
        with st.container(border=True):
            _section_header("Top Persistent Clusters", icon="schedule")
            if not filtered_clusters.empty:
                window_col = f"persistence_{config.PERSISTENCE_DEFAULT_WINDOW_DAYS}d"
                top = filtered_clusters.sort_values(window_col, ascending=False).head(8)
                st.dataframe(
                    top[["grid_cell", window_col, "detection_count", "avg_frp", "risk_score", "risk_level"]]
                    .rename(columns={window_col: "days_active"}),
                    hide_index=True, width="stretch",
                )
            else:
                st.caption("No persistent clusters in the current filter selection.")


def _render_live_map(filtered, label_field, color_by):
    with st.container(border=True):
        hdr, back_btn, globe_btn, toggle = st.columns([2.4, 1.3, 1.3, 1.0])
        with hdr:
            _section_header(f"Live Map — {len(filtered)} hotspots (Jharkhand–Odisha Belt)", icon="map")
        with back_btn:
            st.button("Return to India", key="back_india_livemap", width="stretch", icon=":material/arrow_back:",
                      on_click=_navigate(page="Live Map", region="india"))
        with globe_btn:
            st.button("3D Holo Globe", key="livemap_open_3d_globe", width="stretch", icon=":material/public:",
                      help="Open interactive 3D orbital globe view",
                      on_click=_navigate(page="3D Holo Globe"))
        timelapse_on = toggle.toggle("Time-lapse")
        if filtered.empty:
            st.info("No hotspots match the current filters.", icon=":material/search_off:")
        elif timelapse_on:
            if len(filtered) > TIMELAPSE_MAX_POINTS:
                st.caption(f"Showing the {TIMELAPSE_MAX_POINTS} most recent of {len(filtered)} points for smooth playback.")
            st_folium(build_timelapse_map(filtered, label_field), width=None, height=660, returned_objects=[], key="map_live_timelapse")
        else:
            st_folium(build_map(filtered, label_field, color_by), width=None, height=660, returned_objects=[], key="map_live")



def _render_alerts_tab(alerts):
    from src.alerts import messages as alert_messages

    phone = st.session_state.get("alert_phone", config.ALERT_RECIPIENT_PHONE)
    auto_active = st.session_state.get("alert_auto_dispatch", config.ALERT_AUTO_DISPATCH_CRITICAL)

    # Critical Alert Gateway Status & Quick Action Card
    with st.container(border=True):
        w1, w2, w3 = st.columns([3, 2.2, 1.6])
        with w1:
            _section_header("Critical Alert SMS & Message Dispatch (Automated)", icon="sms", icon_color="var(--accent-critical)")
            st.markdown(
                f'<div style="font-size:0.85rem;color:var(--ink);">'
                f'<b>Recipient:</b> <span class="mono" style="color:#4d8fc4;font-weight:600;">{phone}</span> &middot; '
                f'<b>Trigger Rule:</b> <span class="mono" style="color:#e66767;font-weight:600;">Severity = CRITICAL (Risk &ge; {config.ALERT_CRITICAL_RISK_MIN})</span> &middot; '
                f'<b>Auto-Notify:</b> <span class="mono" style="color:{"#0ca30c" if auto_active else "#fab219"};">{"ENABLED" if auto_active else "DISABLED"}</span>'
                f'<div style="color:var(--ink2);font-size:0.75rem;margin-top:4px;">'
                f'Automated dispatch instantly transmits SMS and messaging alerts to field responders when CRITICAL thermal events are detected.'
                f'</div></div>',
                unsafe_allow_html=True,
            )
        with w2:
            st.markdown(
                '<div style="font-size:0.78rem;padding:6px 10px;border-radius:4px;background:rgba(230,103,103,0.08);border:1px solid rgba(230,103,103,0.25);color:var(--ink);line-height:1.4;">'
                ':material/warning: <b>Critical Alert Message Template:</b><br>'
                '<span class="mono" style="font-size:0.72rem;color:var(--ink2);">'
                ':material/warning: CRITICAL THERMAL EVENT DETECTED<br>'
                'A high-priority persistent hotspot requires immediate verification.<br>'
                'Status: Requires immediate verification.'
                '</span></div>',
                unsafe_allow_html=True,
            )
        with w3:
            sample_event = alerts[0] if alerts else {
                "event_id": "TH-DEMO-CRIT",
                "latitude": 22.8046, "longitude": 86.1850,
                "risk_score": 88.0, "risk_level": "CRITICAL",
                "severity": "CRITICAL",
                "classification": "Likely Industrial Fire",
                "ai_confidence": 94.5, "frp": 16.2, "persistence_days": 24,
                "industrial_distance_km": 0.12, "status": "Requires immediate verification.",
            }
            if st.button("Test Critical SMS / Message", key="msg_send_test_top", width="stretch", icon=":material/sms:", help=f"Send test critical notification to {phone}"):
                res = alert_messages.send_critical_alert(sample_event, phone=phone, force=True)
                if res["status"] in ("delivered", "simulated"):
                    st.toast(f"Critical alert message dispatched to {phone}!", icon=":material/sms:")
                    st.success(f"Dispatched to {phone} ({res['detail']})", icon=":material/check_circle:")
                else:
                    st.error(f"Failed: {res.get('detail', 'Unknown error')}", icon=":material/cancel:")

        with st.expander("Critical Alert Message Audit Log", expanded=False):
            logs = alert_messages.load_critical_dispatch_log()
            if not logs:
                st.caption("No critical message notifications logged yet in this session.")
            else:
                log_df = pd.DataFrame(logs)[["timestamp", "recipient", "event_id", "risk_score", "severity", "status", "channel", "detail"]]
                st.dataframe(log_df, hide_index=True, width="stretch")

    if not alerts:
        st.info("No alerts generated from the current dataset.", icon=":material/info:")
        return

    sev_color = {"CRITICAL": "#e66767", "HIGH": "#ec835a", "MODERATE": "#fab219"}
    for i, a in enumerate(alerts[:50]):
        color = sev_color.get(a["severity"], "#888")
        event_id = a.get("event_id", a.get("grid_cell", "?"))
        risk_val = float(a.get("risk_score", 0))
        ai_conf = float(a.get("ai_confidence", 85.0))
        is_crit = a.get("severity") == "CRITICAL" or risk_val >= config.ALERT_CRITICAL_RISK_MIN

        crit_badge_html = ""
        if is_crit:
            crit_badge_html = (
                f'<div style="margin-top:6px;display:inline-flex;align-items:center;gap:6px;'
                f'padding:3px 8px;border-radius:4px;background:rgba(230,103,103,0.12);'
                f'border:1px solid rgba(230,103,103,0.35);font-size:0.75rem;color:#e66767;font-family:var(--font-mono,monospace);">'
                f':material/warning: <b>AUTO-NOTIFIED (CRITICAL)</b> &middot; Recipient: {phone} &middot; Risk: {risk_val:.1f}/100 &middot; AI Conf: {ai_conf:.1f}%</div>'
            )

        st.markdown(
            f'<div class="alertcard" style="--sev:{color}"><div class="title">:material/warning: {a["title"]} '
            f'<span class="mono" style="color:var(--ink2);font-size:.75em;">&middot; {event_id}</span></div>'
            f'<div class="meta">Location: {a["latitude"]:.3f}, {a["longitude"]:.3f} &middot; '
            f'Classification: {a["classification"]} &middot; Risk: {risk_val:.1f}/100 &middot; '
            f'AI Confidence: {ai_conf:.1f}% &middot; '
            f'Persistence: {a["persistence_days"]}d &middot; FRP: {a["frp"]:.1f} MW &middot; '
            f'Status: {a["status"]}</div>'
            f'{crit_badge_html}</div>',
            unsafe_allow_html=True,
        )

        b1, b2, b3 = st.columns([1.2, 1.2, 1.6])
        b1.button("View on Map", key=f"alert_view_{i}", width="stretch", disabled=True, help="Switch to the Live Map tab and locate this cell manually.")
        b2.button("Investigate", key=f"alert_inv_{i}", width="stretch", disabled=True, help="Open the Investigations tab and select this grid cell.")
        if b3.button("Send Critical Alert", key=f"alert_crit_send_{i}", width="stretch", icon=":material/sms:", help=f"Dispatch critical notification to {phone}"):
            res = alert_messages.send_critical_alert(a, phone=phone, force=True)
            if res["status"] in ("delivered", "simulated"):
                st.toast(f"Critical alert message dispatched for {event_id} to {phone}!", icon=":material/sms:")
            else:
                st.error(f"Dispatch failed: {res.get('detail', 'Error')}", icon=":material/cancel:")


def _render_analytics(filtered, filtered_clusters, run_info):
    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            _section_header("Classification Distribution", icon="pie_chart")
            if not filtered.empty:
                counts = filtered["rule_label"].value_counts()
                fig = go.Figure(go.Bar(x=counts.values, y=counts.index, orientation="h",
                                        marker_color=[CATEGORY_COLORS.get(l, "#888") for l in counts.index]))
                fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10), template="plotly_dark",
                                   paper_bgcolor="#131415", plot_bgcolor="#131415", yaxis=dict(autorange="reversed"))
                st.plotly_chart(fig, width="stretch")
    with c2:
        with st.container(border=True):
            _section_header("Risk Distribution", icon="warning", icon_color="var(--accent-high)")
            if not filtered.empty:
                counts = filtered["risk_level"].value_counts().reindex(["LOW", "MODERATE", "HIGH", "CRITICAL"]).fillna(0)
                fig = go.Figure(go.Bar(x=counts.index, y=counts.values,
                                        marker_color=[RISK_COLORS[l] for l in counts.index]))
                fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10), template="plotly_dark",
                                   paper_bgcolor="#131415", plot_bgcolor="#131415")
                st.plotly_chart(fig, width="stretch")

    c3, c4 = st.columns(2)
    with c3:
        with st.container(border=True):
            _section_header("Persistence Distribution (days active)", icon="schedule")
            if not filtered.empty:
                st.bar_chart(filtered["persistence_days"].value_counts().sort_index())
    with c4:
        with st.container(border=True):
            _section_header("FRP Distribution (MW)", icon="local_fire_department")
            if not filtered.empty:
                fig = go.Figure(go.Histogram(x=filtered["frp"], marker_color="#4d8fc4", nbinsx=30))
                fig.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=10), template="plotly_dark",
                                   paper_bgcolor="#131415", plot_bgcolor="#131415")
                st.plotly_chart(fig, width="stretch")

    if run_info:
        ml = run_info.get("ml_metrics", {})
        if ml.get("trained"):
            with st.container(border=True):
                _section_header("Feature Importance", icon="insights")
                imp = pd.Series(ml["feature_importances"]).sort_values()
                st.bar_chart(imp)
                st.markdown(f'<div class="caveat">{ml.get("caveat", "")}</div>', unsafe_allow_html=True)

    with st.container(border=True):
        _section_header("Cluster Analysis — nearby events grouped into candidate sites", icon="scatter_plot")
        st.caption("DBSCAN over event coordinates (haversine distance, default 2km radius / 2+ events) — groups "
                   "adjacent ~1km grid-cell events that plausibly belong to one larger real-world site. This is a "
                   "spatial grouping heuristic, not a claim that grouped events share one cause.")
        if filtered_clusters is None or filtered_clusters.empty:
            st.caption("No events in the current filter selection.")
        else:
            _, spatial_summary = find_spatial_clusters(filtered_clusters)
            if spatial_summary.empty:
                st.caption("No multi-event spatial clusters found in the current filter selection — events are "
                           "spread out, or too few to group.")
            else:
                st.dataframe(
                    spatial_summary.rename(columns={
                        "spatial_cluster_id": "Cluster", "n_events": "Events", "total_detections": "Detections",
                        "avg_risk": "Avg Risk", "max_risk": "Max Risk", "latitude": "Latitude", "longitude": "Longitude",
                    }),
                    hide_index=True, width="stretch",
                )

    with st.container(border=True):
        _section_header("Emerging Thermal Sources", icon="trending_up")
        st.caption("Not yet persistent, but recently active with rising FRP relative to their own short history — "
                   "worth watching before they cross the persistence threshold.")
        if filtered_clusters is None or filtered_clusters.empty:
            st.caption("No events in the current filter selection.")
        else:
            candidates = filtered_clusters[
                (~filtered_clusters.get("is_persistent", pd.Series(dtype=bool)).astype(bool))
                & (filtered_clusters.get("detection_count", 0) >= 2)
                & (filtered_clusters.get("has_baseline", False).astype(bool))
                & (filtered_clusters.get("frp_change_pct", 0) > 20)
            ].sort_values("frp_change_pct", ascending=False)
            if candidates.empty:
                st.caption("No emerging sources in the current filter selection.")
            else:
                cols = [c for c in ["event_id", "grid_cell", "detection_count", "frp_baseline_mean",
                                     "latest_frp", "frp_change_pct", "risk_score", "zone_type"] if c in candidates.columns]
                st.dataframe(
                    candidates[cols].rename(columns={"frp_change_pct": "FRP Change %", "frp_baseline_mean": "Baseline FRP",
                                                       "latest_frp": "Latest FRP"}),
                    hide_index=True, width="stretch",
                )


def _render_investigations(filtered_clusters, filtered_detail, analyst_mode: bool):
    if filtered_clusters is None or filtered_clusters.empty:
        st.info("No clusters match the current filters.", icon=":material/search_off:")
        return
    window_col = f"persistence_{config.PERSISTENCE_DEFAULT_WINDOW_DAYS}d"
    table = filtered_clusters.sort_values(window_col, ascending=False).reset_index(drop=True)
    table.insert(0, "rank", range(1, len(table) + 1))

    _section_header("Top Persistent Clusters — select a row to investigate", icon="schedule")
    display_cols = ["rank", "event_id", "grid_cell", window_col, "detection_count", "avg_frp", "max_frp",
                     "dominant_label", "risk_score", "risk_level", "status", "latitude", "longitude"]
    display_cols = [c for c in display_cols if c in table.columns]
    event = st.dataframe(
        table[display_cols].rename(columns={window_col: "days_active"}),
        hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
    )

    selected_idx = event.selection.rows if hasattr(event, "selection") else []
    if selected_idx:
        cell = table.iloc[selected_idx[0]]["grid_cell"]
        st.session_state["selected_cell"] = cell

    if st.session_state.get("selected_cell"):
        cell = st.session_state["selected_cell"]
        cluster_row = filtered_clusters[filtered_clusters["grid_cell"] == cell]
        detail_rows = filtered_detail[filtered_detail["grid_cell"] == cell] if not filtered_detail.empty else pd.DataFrame()
        if not cluster_row.empty:
            st.divider()
            render_investigation_panel(cluster_row.iloc[0], detail_rows, analyst_mode)
        else:
            st.caption("Selected cluster is outside the current filter selection.")


def _render_data_tab(filtered, run_info):
    with st.container(border=True):
        _section_header("System Health", icon="monitor_heart")
        h1, h2, h3, h4, h5 = st.columns(5)
        firms_ok = (run_info or {}).get("hotspot_source") in ("firms_live", "local_cache")
        osm_ok = (run_info or {}).get("zone_source") in ("overpass_live", "cache")
        landcover_ok = (run_info or {}).get("landcover_source") in ("overpass_live", "cache", "cache_stale")
        h1.markdown(_pill("NASA FIRMS: " + ("ONLINE" if firms_ok else "CACHED/DEMO"), "#0ca30c" if firms_ok else "#fab219", icon="check_circle" if firms_ok else "cached"), unsafe_allow_html=True)
        h2.markdown(_pill("OSM Industrial: " + ("AVAILABLE" if osm_ok else "CACHED/DEMO"), "#0ca30c" if osm_ok else "#fab219", icon="check_circle" if osm_ok else "cached"), unsafe_allow_html=True)
        h3.markdown(_pill("OSM Landcover: " + ("AVAILABLE" if landcover_ok else "UNAVAILABLE"), "#0ca30c" if landcover_ok else "#6b6e72", icon="check_circle" if landcover_ok else "cancel"), unsafe_allow_html=True)
        h4.markdown(_pill("Database: HEALTHY" if config.DB_PATH.exists() else "DATABASE: NOT YET CREATED", "#0ca30c" if config.DB_PATH.exists() else "#6b6e72", icon="check_circle" if config.DB_PATH.exists() else "cancel"), unsafe_allow_html=True)
        h5.markdown(_pill("ML Model: LOADED" if config.MODEL_PATH.exists() else "ML MODEL: NOT YET TRAINED", "#0ca30c" if config.MODEL_PATH.exists() else "#6b6e72", icon="check_circle" if config.MODEL_PATH.exists() else "cancel"), unsafe_allow_html=True)
        if run_info:
            st.caption(f"Records processed this run: {(run_info or {}).get('n_stored_total', 'n/a')} accumulated in store. "
                       f"Landcover zones loaded: {(run_info or {}).get('n_landcover_zones', 'n/a')} "
                       f"(forest/water/farmland — feeds wildfire/agri-burn evidence; not used when unavailable).")

    with st.container(border=True):
        _section_header("Hotspot Table", icon="table_chart")
        cols = ["grid_cell", "acq_date", "acq_time", "latitude", "longitude", "frp", "confidence_numeric",
                "persistence_days", "rule_label", "ml_label", "risk_score", "risk_level", "industrial_distance_km", "status"] \
            if "status" in filtered.columns else \
            ["grid_cell", "acq_date", "acq_time", "latitude", "longitude", "frp", "confidence_numeric",
             "persistence_days", "rule_label", "ml_label", "risk_score", "risk_level", "industrial_distance_km"]
        cols = [c for c in cols if c in filtered.columns]
        search = st.text_input("Search classification / grid cell")
        table = filtered[cols].sort_values("acq_date", ascending=False)
        if search:
            mask = table.astype(str).apply(lambda col: col.str.contains(search, case=False, na=False)).any(axis=1)
            table = table[mask]
        st.dataframe(table, width="stretch", hide_index=True)
        st.download_button("Download CSV", table.to_csv(index=False), "hotspots.csv", "text/csv")

    with st.container(border=True):
        _section_header("Data Provenance", icon="history")
        st.markdown(
            "- **NASA FIRMS** — satellite thermal hotspot data (VIIRS/MODIS)\n"
            "- **OpenStreetMap** — industrial/mining geospatial context (via Overpass)\n"
            "- **GeoPandas / Shapely** — spatial processing\n"
            "- **scikit-learn** — Random Forest validation layer\n\n"
            f"Data window: rolling {config.FIRMS_TOTAL_DAYS} days · Region: {config.REGION_NAME}"
        )

    with st.container(border=True):
        _section_header("Analyst Review Audit Trail", icon="fact_check")
        reviews = store.load_reviews(region="jharkhand_odisha")
        if reviews.empty:
            st.caption("No analyst decisions recorded yet — see the Validation page or an event's "
                       "investigation panel to record one.")
        else:
            st.dataframe(
                reviews.sort_values("reviewed_at", ascending=False)[["event_id", "grid_cell", "decision", "notes", "reviewed_at"]],
                hide_index=True, width="stretch",
            )
            st.caption("Persistent SQLite record (`data/hotspots.db`, `analyst_reviews` table) — the latest "
                       "decision per event with a timestamp, not a full multi-review history log.")


def _render_model_tab(run_info):
    ml = (run_info or {}).get("ml_metrics", {})
    if not ml.get("trained"):
        st.warning(ml.get("reason", "Model not yet trained — run the pipeline first.") if ml else "Run the pipeline first to train and evaluate the model.", icon=":material/warning:")
        return

    st.caption(f"Model version **{ml.get('version', 'unknown')}** &middot; trained {ml.get('trained_at', 'unknown')} "
               f"&middot; {ml.get('n_train', 0)} training rows / {ml.get('n_total_available', '?')} available "
               f"&middot; Random Forest (200 trees, max depth 8)", unsafe_allow_html=True)

    m1, m2, m3, m4 = st.columns(4)
    m1.markdown(f'<div class="stat"><div class="lbl">Accuracy</div><div class="val">{ml["accuracy"]:.0%}</div></div>', unsafe_allow_html=True)
    m2.markdown(f'<div class="stat"><div class="lbl">Precision</div><div class="val">{ml["precision"]:.0%}</div></div>', unsafe_allow_html=True)
    m3.markdown(f'<div class="stat"><div class="lbl">Recall</div><div class="val">{ml["recall"]:.0%}</div></div>', unsafe_allow_html=True)
    m4.markdown(f'<div class="stat"><div class="lbl">F1 Score</div><div class="val">{ml["f1"]:.0%}</div></div>', unsafe_allow_html=True)

    with st.container(border=True):
        _section_header("Confusion Matrix", icon="grid_view")
        cm = ml["confusion_matrix"]
        labels = ml["confusion_labels"]
        fig = go.Figure(go.Heatmap(z=cm, x=labels, y=labels, colorscale="Blues", showscale=False))
        fig.update_layout(height=420, margin=dict(l=10, r=10, t=10, b=10), template="plotly_dark",
                           paper_bgcolor="#131415", plot_bgcolor="#131415",
                           xaxis=dict(title="Predicted"), yaxis=dict(title="Actual", autorange="reversed"))
        st.plotly_chart(fig, width="stretch")

    with st.container(border=True):
        _section_header("Feature Importance", icon="insights")
        st.bar_chart(pd.Series(ml["feature_importances"]).sort_values())

    with st.expander("Full classification report"):
        st.text(ml["classification_report"])

    st.markdown(f'<div class="caveat">{ml["caveat"]}</div>', unsafe_allow_html=True)


# ---------------------------------------------------------- national mode --

NATIONAL_MODES = ["Raw Hotspots", "Events", "Persistent Sources", "Industrial Sources", "High-Risk", "Critical"]


def build_national_map(points: pd.DataFrame, mode: str, show_heatmap: bool) -> folium.Map:
    points = points.copy()
    if "frp" not in points.columns and "avg_frp" in points.columns:
        points["frp"] = points["avg_frp"]  # event-level dataframes use avg_frp; normalize for the heatmap/popup below

    center_lat = (config.INDIA_BBOX["min_lat"] + config.INDIA_BBOX["max_lat"]) / 2
    center_lon = (config.INDIA_BBOX["min_lon"] + config.INDIA_BBOX["max_lon"]) / 2
    m = folium.Map(location=[center_lat, center_lon], zoom_start=5, tiles=None, control_scale=True)
    _add_base_layers(m)

    try:
        from src.national.states import load_states
        states = load_states()

        def _state_style(feature):
            name = feature["properties"].get("state_name", "")
            if name in ("Jharkhand", "Odisha"):
                return {"color": "#fab219", "weight": 2.2, "fillColor": "#fab219", "fillOpacity": 0.12, "dashArray": "3"}
            return {"color": "#4d8fc4", "weight": 1, "fillColor": "#4d8fc4", "fillOpacity": 0.02}

        def _state_highlight(feature):
            name = feature["properties"].get("state_name", "")
            if name in ("Jharkhand", "Odisha"):
                return {"weight": 3.5, "fillOpacity": 0.28, "color": "#ffd255", "fillColor": "#fab219"}
            return {"weight": 2, "fillOpacity": 0.08, "color": "#7fb1e0"}

        folium.GeoJson(
            states, name="State Boundaries",
            style_function=_state_style,
            highlight_function=_state_highlight,
            tooltip=folium.GeoJsonTooltip(
                fields=["state_name"],
                aliases=["State:"],
                style=f"font-family:{FONT_STACK};font-size:12px;background:#131415;color:#e8e9ea;border:1px solid rgba(255,255,255,.2);padding:4px 8px;border-radius:4px;",
            ),
        ).add_to(m)
    except Exception as exc:
        print(f"[app] state boundary layer failed: {exc}")

    # Dedicated interactive Target Region zone for Jharkhand–Odisha Belt
    belt_popup_html = (
        f'<div style="font-family:{FONT_STACK};font-size:12.5px;line-height:1.6;padding:4px;min-width:210px;">'
        f'<b style="color:#fab219;font-size:13px;"><span class="material-symbols-rounded" style="font-size:13px;vertical-align:-2px;">adjust</span> {config.REGION_NAME}</b><br>'
        f'<span style="color:#9a9da1;">Target Industrial &amp; Mining GIS Region</span><br>'
        f'<div style="margin:6px 0;padding:5px 8px;background:rgba(250,178,25,0.12);border-left:3px solid #fab219;border-radius:3px;">'
        f'Full OSM steel/mines layers, AI classification &amp; anomaly detection active.'
        f'</div>'
        f'<span style="font-family:{MONO_STACK};font-size:11px;color:#4d8fc4;"><span class="material-symbols-rounded" style="font-size:11px;vertical-align:-1px;">bolt</span> Click anywhere inside this region to open detailed map</span>'
        f'</div>'
    )
    folium.Rectangle(
        bounds=[[config.BBOX["min_lat"], config.BBOX["min_lon"]], [config.BBOX["max_lat"], config.BBOX["max_lon"]]],
        color="#fab219", weight=2.5, fill=True, fill_color="#fab219", fill_opacity=0.10, dash_array="5, 5",
        tooltip="Click to Access Jharkhand–Odisha Belt Detailed Map",
        popup=folium.Popup(belt_popup_html, max_width=250),
        name="Target Region: Jharkhand–Odisha",
    ).add_to(m)

    # Clickable central target badge for the belt
    belt_center_lat = (config.BBOX["min_lat"] + config.BBOX["max_lat"]) / 2
    belt_center_lon = (config.BBOX["min_lon"] + config.BBOX["max_lon"]) / 2
    folium.Marker(
        location=[belt_center_lat, belt_center_lon],
        icon=folium.DivIcon(
            html=(
                '<div style="cursor:pointer;background:#131415;border:2px solid #fab219;color:#fab219;'
                'border-radius:20px;padding:4px 10px;font-family:\'IBM Plex Mono\',monospace;font-size:11px;'
                'font-weight:600;white-space:nowrap;box-shadow:0 0 12px rgba(250,178,25,0.5);'
                'transform:translate(-50%, -50%);display:flex;align-items:center;gap:6px;'
                'animation:pulse-glow 2.5s infinite;">'
                '<span style="width:8px;height:8px;border-radius:50%;background:#fab219;display:inline-block;"></span>'
                '<span class="material-symbols-rounded" style="font-size:13px;">adjust</span> Access Jharkhand–Odisha Map</div>'
            )
        ),
        tooltip="Click to Access Jharkhand–Odisha Detailed Map",
        popup=folium.Popup(belt_popup_html, max_width=250),
    ).add_to(m)

    if show_heatmap and not points.empty:
        from folium.plugins import HeatMap
        HeatMap(points[["latitude", "longitude", "frp"]].values.tolist(), radius=12, blur=16, max_zoom=6,
                name="Heat Intensity").add_to(m)

    if not points.empty and not show_heatmap:
        cluster = MarkerCluster(disableClusteringAtZoom=8, maxClusterRadius=40,
                                 icon_create_function=CLUSTER_ICON_JS, name="Events").add_to(m)
        for _, row in points.iterrows():
            risk_level_value = row.get("risk_level")
            risk_key = str(risk_level_value).upper() if risk_level_value is not None else "LOW"
            color = RISK_COLORS.get(risk_key, "#4d8fc4")
            risk_score_value = row.get("risk_score", 0)
            risk_pct = max(0.0, min(100.0, float(risk_score_value or 0)))
            frp_value = row.get("frp", row.get("avg_frp", 0))
            frp = float(frp_value) if frp_value is not None else 0.0
            popup = (
                f'<div style="font-family:{FONT_STACK};font-size:12.5px;line-height:1.6;min-width:180px;">'
                f"<b style='color:{color}'>{row.get('event_id', row.get('grid_cell', '?'))}</b><br>"
                f"<span style='color:#9a9da1;'>{row.get('state', 'Unknown state')}</span><br>"
                f'<div style="height:4px;background:rgba(255,255,255,.1);border-radius:2px;margin:.3rem 0 .5rem;">'
                f'<div style="height:100%;width:{risk_pct}%;background:{color};border-radius:2px;"></div></div>'
                f"FRP: {frp:.1f} MW &middot; Risk: {risk_level_value if risk_level_value is not None else '?'}"
                f"</div>"
            )
            folium.CircleMarker(
                location=[row["latitude"], row["longitude"]], radius=4, color=color,
                fill=True, fill_color=color, fill_opacity=0.85, weight=1,
                popup=folium.Popup(popup, max_width=230),
            ).add_to(cluster)

    _add_map_chrome(m, _legend_html("Risk Level", RISK_COLORS))
    return m


def _apply_national_filters(detail_df: pd.DataFrame, page: str):
    show_ui = page == "Live Map"
    states_available = sorted(s for s in detail_df["state"].dropna().unique())
    satellites_available = sorted(detail_df["satellite"].dropna().unique().astype(str))
    frp_max_n = float(detail_df["frp"].max()) if not detail_df.empty else 20.0

    if show_ui:
        with st.container(border=True):
            _section_header("Filters", icon="tune")
            f1, f2, f3, f4 = st.columns(4)
            state_filter = f1.multiselect("State", states_available, default=states_available, key=f"nstate_{page}")
            satellite_filter = f2.multiselect("Satellite", satellites_available, default=satellites_available, key=f"nsat_{page}")
            risk_filter = f3.multiselect("Risk", list(RISK_COLORS.keys()), default=list(RISK_COLORS.keys()), key=f"nrisk_{page}")
            map_mode = f4.selectbox("Map Mode", NATIONAL_MODES, key=f"nmode_{page}")

            g1, g2, g3, g4 = st.columns(4)
            min_conf_n = g1.slider("Min Confidence", 0, 100, 0, key=f"nconf_{page}")
            min_persist_n = g2.slider("Min Persistence (days)", 0, config.NATIONAL_DAY_RANGE, 0, key=f"npers_{page}")
            frp_range_n = g3.slider("FRP Range (MW)", 0.0, max(frp_max_n, 1.0), (0.0, max(frp_max_n, 1.0)), key=f"nfrp_{page}")
            show_heatmap = g4.checkbox("Heatmap layer", key=f"nheat_{page}")
    else:
        state_filter, satellite_filter, risk_filter = states_available, satellites_available, list(RISK_COLORS.keys())
        min_conf_n, min_persist_n = 0, 0
        frp_range_n = (0.0, max(frp_max_n, 1.0))
        map_mode, show_heatmap = "Persistent Sources", False

    mask = (
        detail_df["state"].isin(state_filter) & detail_df["satellite"].astype(str).isin(satellite_filter)
        & detail_df["risk_level"].isin(risk_filter) & (detail_df["confidence_numeric"] >= min_conf_n)
        & (detail_df["persistence_days"] >= min_persist_n) & detail_df["frp"].between(*frp_range_n)
    )
    filtered_detail = detail_df[mask]
    return filtered_detail, state_filter, map_mode, show_heatmap


def _map_points_for_mode(filtered_detail: pd.DataFrame, filtered_events: pd.DataFrame, map_mode: str) -> pd.DataFrame:
    if map_mode == "Raw Hotspots":
        return filtered_detail
    if map_mode == "Persistent Sources":
        return filtered_events[filtered_events["is_persistent"]] if not filtered_events.empty else filtered_events
    if map_mode == "High-Risk":
        return filtered_events[filtered_events["risk_level"] == "HIGH"] if not filtered_events.empty else filtered_events
    if map_mode == "Critical":
        return filtered_events[filtered_events["risk_level"] == "CRITICAL"] if not filtered_events.empty else filtered_events
    if map_mode == "Industrial Sources":
        return filtered_events.iloc[0:0]
    return filtered_events  # Events


# ----------------------------------------------------------- 3D Holo Globe --


def _render_3d_globe_page(filtered_data: pd.DataFrame | gpd.GeoDataFrame | None,
                          filtered_clusters_or_events: pd.DataFrame | None,
                          is_regional: bool = True):
    from src.utils.export_3d_globe import (
        export_pipeline_events_for_holo_view,
        generate_embedded_3d_globe_html,
        load_or_export_holo_events,
    )

    # 1. Page Header with Breadcrumbs & Sync Status
    h1, h2 = st.columns([3.2, 1.8])
    with h1:
        _section_header("3D Holo Globe — Orbital Thermal Risk Radar", icon="public")
        st.caption(":material/public: Real-time 3D planetary digital twin visualizing satellite thermal energy beams, AI risk tiers, and persistence.")
    with h2:
        sync_cols = st.columns([1.2, 1.0])
        with sync_cols[0]:
            if st.button("Sync Live Pipeline", key="sync_3d_globe_top", width="stretch", icon=":material/sync:",
                         help="Transform and sync current detection pipeline data to Holo-View 3D Globe"):
                with st.spinner("Syncing thermal events to 3D Globe..."):
                    if is_regional:
                        gdf = _load_cached_detail()
                        c_df = _load_cached_clusters()
                        events = export_pipeline_events_for_holo_view(gdf, c_df)
                    else:
                        info = st.session_state.get("national_info")
                        events = export_pipeline_events_for_holo_view(
                            events_df=info.get("events_df") if info else None,
                            national_detail_df=info.get("detail_df") if info else None,
                        )
                    st.session_state["holo_events_count"] = len(events)
                    st.session_state["holo_last_synced"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
                    st.toast(f"{len(events)} events synced to 3D Holo Globe!", icon=":material/public:")
                    st.rerun()
        with sync_cols[1]:
            if is_regional:
                st.button("2D Live Map", key="back_to_livemap_regional", width="stretch", icon=":material/arrow_back:",
                          on_click=_navigate(page="Live Map", region="jharkhand_odisha"))
            else:
                st.button("2D Live Map", key="back_to_livemap_national", width="stretch", icon=":material/arrow_back:",
                          on_click=_navigate(page="Live Map", region="india"))

    # Load 3D events
    events = load_or_export_holo_events()
    n_events = len(events)
    n_critical = sum(1 for e in events if e.get("riskLevel") == "CRITICAL")
    n_high = sum(1 for e in events if e.get("riskLevel") == "HIGH")
    total_frp = sum(float(e.get("frp", 0)) for e in events)
    last_synced = st.session_state.get("holo_last_synced", "Active session")

    # 2. Stat Row
    _stat_row([
        ("Active 3D Beams", n_events, False, "public", None),
        ("Critical Risk", n_critical, n_critical > 0, "warning", RISK_COLORS["CRITICAL"] if n_critical else None),
        ("High-Risk Events", n_high, n_high > 0, "warning", RISK_COLORS["HIGH"] if n_high else None),
        ("Total Radiative Power", f"{total_frp:.0f} MW", False, "local_fire_department", None),
    ])

    # 3. View Mode and Interactive Control Toolbar
    with st.container(border=True):
        t1, t2, t3, t4 = st.columns([2.0, 1.4, 1.2, 1.4])
        view_mode = t1.radio(
            "Visualization Engine",
            ["Embedded WebGL 3D Globe (Instant)", "Holo-View-Maker React App (Live Server)"],
            horizontal=True,
            key="globe_view_mode",
        )
        color_by = t2.radio("Beam Coloring", ["category", "risk"], horizontal=True, key="globe_color_by",
                            format_func=lambda x: "AI Category" if x == "category" else "Risk Level")
        auto_spin = t3.checkbox("Auto-Rotate Orbit", value=True, key="globe_auto_spin")
        min_risk_val = t4.slider("Min Risk Score", 0, 95, 0, step=5, key="globe_min_risk")

    if view_mode.startswith("Embedded WebGL"):
        # Embedded zero-dependency Three.js WebGL globe
        globe_html = generate_embedded_3d_globe_html(
            events=events,
            color_by=color_by,
            auto_rotate=auto_spin,
            min_risk=min_risk_val,
        )
        st.iframe(globe_html, height=730)

        # Quick guide & tips beneath the globe
        g1, g2 = st.columns([3, 2])
        with g1:
            st.caption(":material/lightbulb: **3D Interaction Guide:** Left-click and drag to orbit around the globe. Scroll to zoom in/out. Click on any vertical energy beam or ground halo to inspect its complete risk telemetry and auto-focus.")
        with g2:
            st.caption(f":material/sensors: **Data Pipeline Status:** {n_events} active thermal sources exported &middot; Last synced: `{last_synced}`")
    else:
        # Live React + Three.js Holo-View-Maker Dev Server (Iframe)
        holo_host = st.session_state.get("holo_host_url", "http://localhost:5173")
        
        i1, i2, i3 = st.columns([2.5, 1.2, 1.3])
        with i1:
            holo_url_input = st.text_input("Holo-View App URL", value=holo_host, key="holo_url_input_box",
                                            help="URL where `holo-view-maker` is running (default: http://localhost:5173)")
            st.session_state["holo_host_url"] = holo_url_input
        with i2:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            holo_url = holo_url_input or "http://localhost:5173"
            st.link_button("Open in New Window", holo_url, width="stretch", icon=":material/open_in_new:",
                           help="Open the standalone React + Three.js application in a full browser tab")
        with i3:
            st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
            if st.button("Refresh Iframe", key="refresh_holo_iframe", width="stretch", icon=":material/refresh:"):
                st.rerun()

        # Iframe component
        st.iframe(holo_url_input or "http://localhost:5173", height=730)

        with st.expander("How to launch the Holo-View-Maker Dev Server locally", expanded=False, icon=":material/build:"):
            st.markdown(
                "If the iframe above shows a connection error, start the local Vite development server with one command:\n"
                "```bash\n"
                "cd holo-view-maker\n"
                "npm install       # or bun install\n"
                "npm run dev       # starts on http://localhost:5173\n"
                "```\n"
                "Once running, refresh this page or open `http://localhost:5173` directly in your browser. All live detections from `app.py` are continuously synchronized into `holo-view-maker/public/data/events.json`."
            )

    # 4. Export & Data Provenance Card
    with st.container(border=True):
        _section_header("3D Holo-View Pipeline Export Details", icon="data_object")
        e1, e2, e3 = st.columns([2.5, 1.5, 1.5])
        with e1:
            st.caption(
                "**Export Destinations:** `holo-view-maker/public/data/events.json` and `output/holo_events.json` &middot; "
                "**Schema:** `ThermalEvent` (TypeScript interface matching `holo-view-maker/src/lib/thermal.ts`)."
            )
        with e2:
            events_json_str = json.dumps(events, indent=2)
            st.download_button("Download events.json", events_json_str, "events.json", "application/json",
                               key="download_holo_json_btn", width="stretch")
        with e3:
            if is_regional:
                st.button("Open Investigations", key="jump_inv_from_globe", width="stretch", icon=":material/manage_search:",
                          on_click=_navigate(page="Investigations"))
            else:
                st.button("Access Belt Map", key="jump_belt_from_globe", width="stretch", icon=":material/map:",
                          on_click=_navigate(page="Live Map", region="jharkhand_odisha"))


def _render_detection_funnel(state_summary: pd.DataFrame, n_observations: int):

    """A staged-architecture explainer: India-wide detection is cheap and
    runs everywhere; the expensive OSM+AI pipeline only ever runs for the
    one region a user has actually drilled into. Shown with real computed
    counts, not illustrative numbers, so it doubles as a live status view."""
    n_states = int(state_summary["state"].notna().sum()) if not state_summary.empty else 0
    belt_info = st.session_state.get("run_info")
    belt_ran = bool(belt_info)
    n_belt_events = len((_load_cached_clusters())) if belt_ran else None
    belt_alerts = _load_cached_alerts() if belt_ran else []
    n_belt_alerts = sum(1 for a in belt_alerts if a.get("severity") in ("CRITICAL", "HIGH")) if belt_ran else None

    def _step(num, title, metric, sub, on):
        cls = "on" if on else "off"
        return (f'<div class="funnel-step {cls}"><div class="fnum">STAGE {num}</div>'
                f'<div class="ftitle">{title}</div><div class="fmetric">{metric}</div>'
                f'<div class="fsub">{sub}</div></div>')

    arrow = '<div class="funnel-arrow">&#8594;</div>'
    steps = [
        _step("01", "India — Detect Everything", f"{n_observations:,}", "satellite observations, no AI/OSM cost", True),
        _step("02", "State — Analyze Distribution", str(n_states), "states with tagged activity", n_states > 0),
        _step("03", "Industrial Region — Investigate", "ACTIVE" if belt_ran else "READY",
              "Jharkhand–Odisha Belt: full OSM + AI pipeline", True),
        _step("04", "Event — Classify", f"{n_belt_events:,}" if belt_ran else "—",
              "rule + ML classified events (belt only)", belt_ran),
        _step("05", "High-Risk — Alert", f"{n_belt_alerts:,}" if belt_ran else "—",
              "critical/high alerts generated", belt_ran and (n_belt_alerts or 0) > 0),
    ]
    html = '<div class="funnel">' + arrow.join(steps) + '</div>'
    st.markdown(html, unsafe_allow_html=True)
    c1, c2, c3 = st.columns([3.8, 1.4, 1.4])
    c1.caption(":material/adjust: **Target Region Ready:** Stages 3-5 contain the detailed geospatial & AI pipeline for the Jharkhand–Odisha Belt.")
    c2.button("Access Belt Map", key="funnel_open_belt", width="stretch", icon=":material/map:",
              on_click=_navigate(page="Live Map", region="jharkhand_odisha"))
    c3.button("3D Holo Globe", key="funnel_open_3d_globe", width="stretch", icon=":material/public:",
              help="Open the interactive 3D Holo Globe",
              on_click=_navigate(page="3D Holo Globe"))


def _render_national_kpis(filtered_detail: pd.DataFrame, filtered_events: pd.DataFrame):
    n_persistent = int(filtered_events["is_persistent"].sum()) if not filtered_events.empty else 0
    n_high = int((filtered_events["risk_level"] == "HIGH").sum()) if not filtered_events.empty else 0
    n_critical = int((filtered_events["risk_level"] == "CRITICAL").sum()) if not filtered_events.empty else 0
    satellites = sorted(filtered_detail["satellite"].dropna().unique().astype(str)) if not filtered_detail.empty else []
    _stat_row([
        ("Satellite Hotspots", len(filtered_detail), False, "satellite_alt", None),
        ("Detected Events", len(filtered_events), False, "flare", None),
        ("Persistent Sources", n_persistent, n_persistent > 0, "schedule", STATUS_COLORS["PERSISTENT"] if n_persistent else None),
        ("High-Risk Events", n_high, n_high > 0, "warning", RISK_COLORS["HIGH"] if n_high else None),
    ])
    _stat_row([
        ("Critical Alerts", n_critical, n_critical > 0, "warning", RISK_COLORS["CRITICAL"] if n_critical else None),
        ("Industrial Events", "See Belt view", False, "factory", None),
        ("States Active", int(filtered_detail["state"].nunique()) if not filtered_detail.empty else 0, False, "map", None),
        ("Satellites", ", ".join(satellites) or "—", False, "satellite_alt", None),
    ])


def _render_national_map_panel(filtered_detail: pd.DataFrame, filtered_events: pd.DataFrame,
                                map_mode: str, show_heatmap: bool, key: str):
    map_points = _map_points_for_mode(filtered_detail, filtered_events, map_mode)
    with st.container(border=True):
        h1, h2, h3 = st.columns([3.0, 1.4, 1.4])
        with h1:
            _section_header(f"National Map — {map_mode} ({len(map_points)} shown)", icon="map")
            st.caption(":material/lightbulb: **Interactive Access:** Click the button to open the detailed Jharkhand–Odisha Belt GIS map.")
        with h2:
            st.button("Access Belt Map", key=f"jump_belt_top_{key}", width="stretch", icon=":material/map:",
                      on_click=_navigate(page="Live Map", region="jharkhand_odisha"))
        with h3:
            st.button("3D Holo Globe", key=f"jump_3d_top_{key}", width="stretch", icon=":material/public:",
                      help="Open interactive 3D orbital globe view",
                      on_click=_navigate(page="3D Holo Globe"))


        if map_mode == "Industrial Sources":
            st.info("Industrial-zone classification requires the OSM geospatial join, which only runs for the detailed "
                    "Jharkhand–Odisha belt (running it for all of India on every load would be far too slow). "
                    "Switch **Region** (top bar) or click above for the detailed belt view.", icon=":material/info:")
        elif map_points.empty:
            st.info("No observations match the current filters.", icon=":material/search_off:")
        else:
            # Region no longer auto-switches on a map click — it was jumping
            # to the Jharkhand–Odisha Belt (and away from the India view)
            # just from clicking near it on the map, with no way to opt out.
            # The "Access Belt Map" button above is the only way in now.
            st_folium(
                build_national_map(map_points, map_mode, show_heatmap),
                width=None,
                height=620,
                returned_objects=[],
                key=key,
            )


def _render_national_top_states_chart(state_summary: pd.DataFrame, state_filter: list[str]):
    with st.container(border=True):
        c1, c2 = st.columns([3, 2])
        with c1:
            _section_header("Top States by Thermal Activity", icon="bar_chart")
        with c2:
            st.button("Access Jharkhand–Odisha Map", key="top_states_access_belt", width="stretch", icon=":material/map:",
                      on_click=_navigate(page="Live Map", region="jharkhand_odisha"))
        if state_summary.empty:
            st.caption("No state summary available yet.")
            return
        top_states = state_summary[state_summary["state"].isin(state_filter)].head(10)
        fig = go.Figure(go.Bar(x=top_states["hotspots"], y=top_states["state"], orientation="h", marker_color="#4d8fc4"))
        fig.update_layout(height=340, margin=dict(l=10, r=10, t=10, b=10), template="plotly_dark",
                           paper_bgcolor="#131415", plot_bgcolor="#131415", yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, width="stretch")


def _render_national_analytics(filtered_detail: pd.DataFrame, filtered_events: pd.DataFrame,
                                state_summary: pd.DataFrame, state_filter: list[str]):
    c1, c2 = st.columns(2)
    with c1:
        _render_national_top_states_chart(state_summary, state_filter)
    with c2:
        with st.container(border=True):
            _section_header("Risk Distribution (Events)", icon="warning", icon_color="var(--accent-high)")
            if filtered_events.empty:
                st.caption("No events in the current filter selection.")
            else:
                counts = filtered_events["risk_level"].value_counts().reindex(["LOW", "MODERATE", "HIGH", "CRITICAL"]).fillna(0)
                fig = go.Figure(go.Bar(x=counts.index, y=counts.values, marker_color=[RISK_COLORS[l] for l in counts.index]))
                fig.update_layout(height=340, margin=dict(l=10, r=10, t=10, b=10), template="plotly_dark",
                                   paper_bgcolor="#131415", plot_bgcolor="#131415")
                st.plotly_chart(fig, width="stretch")

    with st.container(border=True):
        _section_header("Hotspots / Persistent / High-Risk by State", icon="map")
        if not state_summary.empty:
            st.dataframe(
                state_summary[state_summary["state"].isin(state_filter)]
                .rename(columns={"hotspots": "Hotspots", "persistent_sources": "Persistent",
                                  "high_risk": "High-Risk", "critical": "Critical"}),
                hide_index=True, width="stretch",
            )


def _render_national_data_page(info: dict):
    with st.container(border=True):
        _section_header("System Health", icon="monitor_heart")
        h1, h2 = st.columns(2)
        firms_ok = info.get("hotspot_source") in ("firms_live", "local_cache")
        h1.markdown(_pill("NASA FIRMS: " + ("ONLINE" if firms_ok else "CACHED/DEMO"), "#0ca30c" if firms_ok else "#fab219",
                           icon="check_circle" if firms_ok else "cached"),
                    unsafe_allow_html=True)
        boundary_ok = config.INDIA_STATES_PATH.exists()
        h2.markdown(_pill("India Boundary Data: " + ("LOADED" if boundary_ok else "NOT FOUND"),
                           "#0ca30c" if boundary_ok else "#e66767",
                           icon="check_circle" if boundary_ok else "cancel"), unsafe_allow_html=True)

    with st.container(border=True):
        _section_header("Historical Accumulation", icon="history")
        if info.get("used_accumulated_history"):
            st.caption(
                f"Persistence is judged against **{info.get('history_days_covered', 0)} days** of real accumulated "
                f"history in the national store (`data/national_hotspots.db`), up to a "
                f"{config.NATIONAL_HISTORY_DAYS}-day rolling window — not just this run's latest "
                f"{config.NATIONAL_DAY_RANGE * 24}h fetch. Every live run merges its fresh pull into this store "
                "(deduplicated by location/date/satellite); Demo Mode never touches it."
            )
        else:
            st.caption(
                f"No accumulated history yet for this run — persistence is judged only against the latest "
                f"{config.NATIONAL_DAY_RANGE * 24}h fetch (or Demo Mode's synthetic dataset). Run the pipeline in "
                "live mode a few times across different days to build up real history."
            )

    with st.container(border=True):
        _section_header("Data Quality & Observation Notes", icon="fact_check")
        report = info.get("clean_report", {})
        detail_df = info.get("detail_df")
        n_untagged = int(detail_df["state"].isna().sum()) if detail_df is not None and "state" in detail_df.columns else 0
        st.caption(
            f"Input rows: {report.get('input_rows', '?')} · Output rows after cleaning: {report.get('output_rows', '?')} · "
            f"Dropped (invalid/duplicate/out-of-window): "
            f"{report.get('dropped_invalid_coords', 0) + report.get('dropped_duplicates', 0)} · "
            f"Outside any mapped Indian state polygon (territorial waters/neighboring countries within the "
            f"India bounding box): {n_untagged}"
        )
        st.markdown(
            '<div class="caveat">Absence of a detection does not mean absence of thermal activity — cloud cover, '
            'smoke, satellite pass timing, and fire size/intensity all affect whether FIRMS registers a hotspot. '
            'Terminology on this page ("Satellite Hotspots", "Detected Events") deliberately avoids implying every '
            'point is a confirmed fire.</div>',
            unsafe_allow_html=True,
        )

    with st.container(border=True):
        _section_header("Observations Table", icon="table_chart")
        detail_df = info["detail_df"]
        st.dataframe(detail_df.sort_values("acq_date", ascending=False).head(500), hide_index=True, width="stretch")
        st.download_button("Export CSV", detail_df.to_csv(index=False), "national_observations.csv", "text/csv",
                            key="national_export")


def _render_settings_national(demo_mode: bool):
    with st.container(border=True):
        _section_header("Pipeline", icon="tune")
        api_key_input = None
        if not demo_mode:
            if config.FIRMS_API_KEY:
                st.success("FIRMS_API_KEY loaded from .env", icon=":material/check_circle:")
            else:
                st.warning("No FIRMS_API_KEY configured — pipeline will fall back to cache/demo data.", icon=":material/warning:")
            api_key_input = st.text_input("Or paste a FIRMS key for this session", type="password", key="settings_nat_key")
        if st.button("Run Pipeline", key="settings_nat_run", width="stretch", icon=":material/play_circle:"):
            run_national_and_cache(demo_mode, api_key_input or None)
            st.rerun()
        st.caption("Or switch **Region** (top bar) to Jharkhand–Odisha Belt to run the detailed pipeline instead.")

    with st.container(border=True):
        _section_header("View", icon="visibility")
        st.session_state["presentation_mode"] = st.toggle("Presentation Mode", value=st.session_state["presentation_mode"],
                                                            key="presentation_mode_toggle_national",
                                                            help="Hide technical/admin pages for a clean SIH demo view.")

    with st.container(border=True):
        _section_header("National Operational Parameters", icon="tune")
        st.caption(f"Live fetch per run: latest {config.NATIONAL_DAY_RANGE * 24}h, merged into a persistent store "
                   f"(never touched in Demo Mode). Persistence is then judged over up to a "
                   f"{config.NATIONAL_HISTORY_DAYS}-day rolling window of accumulated history "
                   f"(&ge;{config.NATIONAL_PERSISTENCE_MIN_DAYS_HISTORY} active days &rArr; persistent), falling back "
                   f"to just the fresh batch (&ge;{config.NATIONAL_PERSISTENCE_MIN_DAYS} active days) before any "
                   "history has accumulated. See the Data page for how much history is currently stored.")
        st.caption("National risk weights: " + ", ".join(f"{k} {v:.0%}" for k, v in config.NATIONAL_RISK_WEIGHTS.items()))

    with st.container(border=True):
        _section_header("Critical Alert SMS & Messaging Gateway", icon="sms", icon_color="var(--accent-critical)")
        st.caption("Automated and manual high-priority text alert dispatch to field responders for CRITICAL thermal events.")

        msg1, msg2 = st.columns(2)
        with msg1:
            alert_phone_val = st.text_input(
                "Recipient Phone Number (SMS)",
                value=st.session_state.get("alert_phone", config.ALERT_RECIPIENT_PHONE),
                key="alert_settings_phone_nat",
                help="Target mobile number for automated critical alerts (+country code or 10 digits).",
            )
            st.session_state["alert_phone"] = alert_phone_val
        with msg2:
            alert_auto = st.toggle(
                "Auto-notify on Critical Alerts (Severity = CRITICAL)",
                value=st.session_state.get("alert_auto_dispatch", config.ALERT_AUTO_DISPATCH_CRITICAL),
                key="alert_settings_auto_nat",
                help="Automatically dispatch SMS/messages whenever critical thermal events (Risk >= 76 or CRITICAL severity) are detected.",
            )
            st.session_state["alert_auto_dispatch"] = alert_auto

        send_phone_nat = alert_phone_val or config.ALERT_RECIPIENT_PHONE
        if st.button("Send Test Critical Alert Message to " + send_phone_nat, key="msg_settings_send_test_nat", width="stretch", icon=":material/sms:"):
            from src.alerts import messages as alert_messages
            sample_event = {
                "event_id": "TH-INDIA-CRIT",
                "latitude": 22.8046, "longitude": 86.1850,
                "risk_score": 88.5, "risk_level": "CRITICAL",
                "severity": "CRITICAL",
                "classification": "Likely Industrial Fire",
                "ai_confidence": 94.2, "frp": 16.5, "persistence_days": 24,
                "industrial_distance_km": 0.15, "status": "Requires immediate verification.",
            }
            res = alert_messages.send_critical_alert(
                sample_event,
                phone=send_phone_nat,
                force=True,
            )
            if res["status"] in ("delivered", "simulated"):
                st.success(f"Critical alert message dispatched successfully to {send_phone_nat} ({res['detail']})!", icon=":material/check_circle:")
                st.toast(f"Dispatched to {send_phone_nat}", icon=":material/sms:")
            else:
                st.error(f"Dispatch failed: {res.get('detail', 'Unknown error')}", icon=":material/cancel:")

    with st.container(border=True):
        _section_header("3D Holo Globe & Digital Twin Integration", icon="public")
        st.caption("Real-time synchronization between the Python intelligence pipeline and the Holo-View-Maker 3D WebGL Globe.")

        holo_host_nat = st.text_input(
            "Holo-View App URL / Port",
            value=st.session_state.get("holo_host_url", "http://localhost:5173"),
            key="settings_holo_url_nat",
            help="Local or remote URL where the Holo-View-Maker React/Three.js application is running.",
        )
        st.session_state["holo_host_url"] = holo_host_nat

        c1, c2 = st.columns(2)
        with c1:
            events_synced = st.session_state.get("holo_events_count", len(load_or_export_holo_events()))
            st.markdown(
                f'<div style="font-size:0.83rem;color:var(--ink);line-height:1.6;">'
                f'<b>Sync Status:</b> <span class="mono" style="color:#0ca30c;">● ACTIVE</span> &middot; '
                f'<b>Synced Events:</b> <span class="mono">{events_synced}</span><br>'
                f'<b>Last Synced:</b> <span class="mono">{st.session_state.get("holo_last_synced", "Active session")}</span><br>'
                f'<span style="font-size:0.75rem;color:var(--ink2);">Destination: <code>holo-view-maker/public/data/events.json</code></span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        with c2:
            if st.button("Sync Current Pipeline to 3D Globe Now", key="sync_holo_settings_nat", width="stretch", icon=":material/sync:"):
                with st.spinner("Exporting thermal events to 3D Holo Globe..."):
                    info_curr = st.session_state.get("national_info")
                    exported_3d = export_pipeline_events_for_holo_view(
                        events_df=info_curr.get("events_df") if info_curr else None,
                        national_detail_df=info_curr.get("detail_df") if info_curr else None,
                    )
                    st.session_state["holo_events_count"] = len(exported_3d)
                    st.session_state["holo_last_synced"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
                    st.toast(f"Synced {len(exported_3d)} events to 3D Holo Globe!", icon=":material/public:")
                    st.success(f"Successfully exported {len(exported_3d)} events to Holo-View 3D Globe!", icon=":material/check_circle:")


def _route_national_page(page: str, demo_mode: bool):
    if page == "Settings":
        _render_settings_national(demo_mode)
        return

    info = st.session_state.get("national_info")
    if not info:
        st.info("No national data yet. Open **Settings** and click **Run Pipeline** to fetch the latest "
                "observations (Demo Mode works with zero setup).", icon=":material/info:")
        return

    detail_df: pd.DataFrame = info["detail_df"]
    events_df: pd.DataFrame = info["events_df"]
    state_summary: pd.DataFrame = info["state_summary"]
    alerts = _derive_national_alerts(events_df)

    filtered_detail, state_filter, map_mode, show_heatmap = _apply_national_filters(detail_df, page)
    filtered_event_cells = set(filtered_detail["grid_cell"])
    filtered_events = events_df[events_df["grid_cell"].isin(filtered_event_cells)] if not events_df.empty else events_df

    if page == "Overview":
        _render_detection_funnel(state_summary, len(detail_df))
        _render_national_kpis(filtered_detail, filtered_events)
        _render_national_alert_banner(alerts)
        _render_national_top_states_chart(state_summary, state_filter)
        _render_methodology_expander()
    elif page == "Live Map":
        _render_national_map_panel(filtered_detail, filtered_events, map_mode, show_heatmap, key="map_national_livemap")
    elif page == "3D Holo Globe":
        _render_3d_globe_page(filtered_detail, filtered_events, is_regional=False)
    elif page == "Events":
        _render_events_table(filtered_events, "india")

    elif page == "Alerts":
        _render_alerts_tab(alerts)
    elif page == "Analytics":
        _render_national_analytics(filtered_detail, filtered_events, state_summary, state_filter)
    elif page in ("Investigations", "Validation", "AI Model"):
        st.info(f"**{page}** requires the full geospatial + AI pipeline, which only runs for the detailed "
                "Jharkhand–Odisha belt (no rule-based classification or OSM join runs country-wide — see "
                "Data page for why).", icon=":material/info:")
        st.button(f"Access Jharkhand–Odisha Belt to Open {page}",
                  key=f"nav_restricted_{page}", icon=":material/map:",
                  on_click=_navigate(page=page, region="jharkhand_odisha"))
    elif page == "Data":
        _render_national_data_page(info)
        _render_methodology_expander()


def _render_national_alert_banner(alerts: list[dict]):
    _render_alert_banner(alerts)


if __name__ == "__main__":
    main()
