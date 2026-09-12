"""Thermal Intelligence: the command-centre dashboard for SIH26162.

AI-assisted early-warning and prioritization platform for industrial fires
and persistent thermal sources. This is NOT an autonomous system that
confirms fires, and satellite detection is NOT ground truth. See the
"Requires Verification" category and every risk/confidence figure's own
caveats.

Run with: streamlit run app.py
"""
from __future__ import annotations

import json
import urllib.request

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
# holo-view-maker's Vite dev server (its vite config pins port 8080)
HOLO_DEFAULT_URL = "http://localhost:8080"

st.set_page_config(page_title="Thermal Intelligence", layout="wide", page_icon=":material/local_fire_department:", initial_sidebar_state="expanded")


@st.cache_resource(show_spinner=False)
def _shared_runs() -> dict[str, dict]:
    """One dict shared by every session and rerun, so a pipeline run completed
    in one browser tab is adopted instantly by every other tab and by later
    sessions, with no recompute, no FIRMS transactions. Must be cache_resource:
    Streamlit re-executes this script on every rerun, so a plain module-level
    global would reset each time. Lost on server restart, which is intended:
    a restart should be free to pull fresh data rather than serve stale."""
    return {}

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
# Risk is a state, so it wears the reserved status palette (good / warning /
# serious / critical), never a categorical hue, and always carries its label.
RISK_COLORS = {"LOW": "#0ca30c", "MODERATE": "#fab219", "HIGH": "#ec835a", "CRITICAL": "#d03b3b"}
STATUS_COLORS = {
    "NEW": "#5cb8dc", "RECURRING": "#a1adba", "PERSISTENT": "#fab219",
    "HIGH RISK": "#ec835a", "CRITICAL": "#d03b3b", "RESOLVED/INACTIVE": "#71808f",
}
# Shared page tokens, mirrored from the CSS above so folium and plotly (which
# never see the stylesheet) draw on the same surfaces as everything else.
INK, INK2, MUTED = "#e4eaf0", "#a1adba", "#71808f"
SERIES = "#3987e5"  # single-series charts; the accent is reserved for actions
SURFACE, SURFACE_2, LINE = "#10161d", "#151d26", "#1d2733"
ACCENT = "#5cb8dc"

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500;600&display=swap');

/* One token set, shared with the globe app (holo-view-maker/src/styles.css).
   One accent, used only for actions, selection and focus; risk keeps its own
   status palette and never borrows the accent. */
:root{
  --page:#0a0e13; --surface:#10161d; --surface-2:#151d26; --surface-3:#1b2531;
  --line:#1d2733; --line-strong:#2a3848;
  --ink:#e4eaf0; --ink2:#a1adba; --muted:#71808f;
  --accent:#5cb8dc; --on-accent:#061018;
  --good:#0ca30c; --warn:#fab219; --serious:#ec835a; --critical:#d03b3b;
  --radius:6px; --ease:cubic-bezier(0.23,1,0.32,1); --dur:160ms;
}
html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"], p, label, button, input, select, textarea {
  font-family:'IBM Plex Sans',system-ui,-apple-system,'Segoe UI',sans-serif !important;
}
body{ -webkit-font-smoothing:antialiased; }
.mono{ font-family:'IBM Plex Mono',ui-monospace,monospace; font-variant-numeric:tabular-nums; }

::selection{ background:rgba(92,184,220,.28); color:var(--ink); }
*{ scrollbar-width:thin; scrollbar-color:var(--line-strong) transparent; }
*::-webkit-scrollbar{ width:10px; height:10px; }
*::-webkit-scrollbar-thumb{ background:var(--line-strong); border-radius:99px; border:3px solid transparent; background-clip:content-box; }
*::-webkit-scrollbar-thumb:hover{ background:#3a4a5d; background-clip:content-box; }
*::-webkit-scrollbar-track{ background:transparent; }
:focus-visible{ outline:2px solid var(--accent); outline-offset:2px; border-radius:3px; }

h1,h2,h3,h4,h5{ letter-spacing:-.01em; }

/* Motion: one entrance and one growth keyframe, both on the shared --dur/--ease
   tokens. Fast and non-repeating — this settles content in on a rerun rather
   than performing an "orchestrated" reveal, and stays well under 300ms so it
   reads as responsive even when Streamlit's rerun model replays it often. */
@keyframes ti-fade-up{ from{ opacity:0; transform:translateY(4px); } to{ opacity:1; transform:translateY(0); } }
@keyframes ti-grow-x{ from{ transform:scaleX(0); } to{ transform:scaleX(1); } }
.statrow, .panel, .alertcard, .alertbar, [data-testid="stVerticalBlock"]{
  animation:ti-fade-up 140ms var(--ease) both;
}

/* Top bar */
.topbar-brand h1{ margin:0 0 .25rem; font-size:1.25rem; font-weight:600; color:var(--ink); }
.topbar-brand .sub{ margin:0; color:var(--ink2); font-size:.8rem; }
.topbar-meta{ font-size:.78rem; color:var(--ink2); line-height:1.7; padding-top:.2rem; }
.topbar-meta .v{ font-family:'IBM Plex Mono',monospace; font-variant-numeric:tabular-nums; color:var(--ink); }
.topbar-rule{ border:none; border-top:1px solid var(--line); margin:.9rem 0 1.2rem; }

/* Metric strip: one row, no icons, no colored borders. */
.statrow{ display:grid; grid-template-columns:repeat(4,1fr); border:1px solid var(--line);
  border-radius:var(--radius); overflow:hidden; margin-bottom:.9rem; background:var(--surface); }
.stat{ padding:.8rem 1rem; border-right:1px solid var(--line); }
.stat:last-child{ border-right:none; }
.stat .lbl{ font-size:.78rem; color:var(--ink2); margin-bottom:.3rem; }
.stat .val{ font-family:'IBM Plex Mono',monospace; font-size:1.3rem; font-weight:500;
  color:var(--ink); font-variant-numeric:tabular-nums; letter-spacing:-.01em; }

/* Section headers: sentence case, sans, no icon. */
.sec-hdr{ font-size:.95rem; font-weight:600; color:var(--ink);
  padding-bottom:.5rem; margin-bottom:.85rem; border-bottom:1px solid var(--line); }

.alertbar{ display:flex; align-items:center; justify-content:space-between; gap:1rem;
  border:1px solid var(--line-strong); background:var(--surface-2);
  border-radius:var(--radius); padding:.75rem 1rem; margin-bottom:1rem; }
.alertbar .txt{ font-size:.88rem; color:var(--ink); }
.alertbar .txt b{ font-family:'IBM Plex Mono',monospace; font-variant-numeric:tabular-nums; }
.alertcard{ border:1px solid var(--line); background:var(--surface);
  border-radius:var(--radius); padding:.75rem 1rem; margin-bottom:.5rem;
  transition:border-color var(--dur) var(--ease); }
.alertcard:hover{ border-color:var(--line-strong); }
.alertcard .title{ font-weight:600; font-size:.88rem; color:var(--ink); display:flex; align-items:center; gap:.5rem; }
.alertcard .title .sev{ width:8px; height:8px; border-radius:2px; background:var(--sev,var(--muted)); flex:none; }
.alertcard .meta{ font-size:.78rem; color:var(--ink2); margin-top:.4rem; line-height:1.6; }
.alertcard .facts{ display:flex; flex-wrap:wrap; gap:.25rem 1.75rem; margin-top:.5rem; }
.alertcard .fact{ display:flex; flex-direction:column; gap:.1rem; }
.alertcard .fact .k{ font-size:.72rem; color:var(--muted); }
.alertcard .fact .v{ font-family:'IBM Plex Mono',monospace; font-size:.82rem;
  font-variant-numeric:tabular-nums; color:var(--ink); }

/* Pills read as text with a small colour marker, never coloured text. */
.pill{ display:inline-flex; align-items:center; gap:6px; font-size:.78rem; color:var(--ink);
  padding:.2rem .6rem; border-radius:var(--radius); border:1px solid var(--line);
  background:var(--surface-2); }
.pill .mark{ width:8px; height:8px; border-radius:2px; background:var(--pill,var(--muted)); flex:none; }

.panel{ border:1px solid var(--line); border-radius:var(--radius); background:var(--surface); padding:1rem 1.15rem;
  transition:border-color var(--dur) var(--ease); }
.panel:hover{ border-color:var(--line-strong); }
.panel .row{ display:flex; justify-content:space-between; gap:1rem; padding:.38rem 0;
  border-bottom:1px solid var(--line); font-size:.84rem; }
.panel .row:last-child{ border-bottom:none; }
.panel .row .k{ color:var(--ink2); }
.panel .row .v{ color:var(--ink); font-family:'IBM Plex Mono',monospace; font-variant-numeric:tabular-nums; text-align:right; }
.evidence{ font-size:.84rem; color:var(--ink2); padding:.3rem 0; border-bottom:1px solid var(--line); }
.evidence:last-child{ border-bottom:none; }

section[data-testid="stSidebar"]{ border-right:1px solid var(--line); }
.brand{ font-size:.95rem; font-weight:600; color:var(--ink); }
.brand-sub{ font-size:.75rem; color:var(--muted); margin-top:.15rem; margin-bottom:.2rem; }

[data-testid="stButton"] button, [data-testid="stDownloadButton"] button, [data-testid="stLinkButton"] a{
  border-radius:var(--radius) !important; font-weight:500 !important; font-size:.83rem !important;
  letter-spacing:0 !important; text-transform:none !important;
  transition:background-color var(--dur) var(--ease), border-color var(--dur) var(--ease),
    transform var(--dur) var(--ease), filter var(--dur) var(--ease) !important; }
[data-testid="stButton"] button:hover, [data-testid="stDownloadButton"] button:hover, [data-testid="stLinkButton"] a:hover{
  filter:brightness(1.14); border-color:var(--accent) !important; }
[data-testid="stButton"] button:active, [data-testid="stDownloadButton"] button:active{ transform:scale(.98); }
section[data-testid="stSidebar"] [data-testid="stButton"] button{ justify-content:flex-start; text-align:left; }

[data-testid="stMetricValue"], [data-testid="stDataFrame"]{ font-variant-numeric:tabular-nums; }

.legend-chip{ display:inline-flex;align-items:center;gap:6px;font-size:.78rem;margin:2px 10px 2px 0;color:var(--ink2); }
.legend-dot{ width:9px;height:9px;border-radius:2px;display:inline-block;flex:none; }

.caveat{ font-size:.78rem; color:var(--muted); border-top:1px solid var(--line); padding-top:.55rem; margin-top:.6rem; line-height:1.65; }

/* Risk explainer: the score broken back into its three weighted components,
   the model's second opinion, and the response that follows from them. */
.risk-lead{ font-size:.9rem; color:var(--ink); line-height:1.55; margin-bottom:.9rem; }
.factors{ display:flex; flex-direction:column; gap:.85rem; }
.factor-head{ display:flex; align-items:baseline; gap:.6rem; font-size:.82rem; }
.factor-head .name{ color:var(--ink); font-weight:500; }
.factor-head .val{ font-family:'IBM Plex Mono',monospace; font-variant-numeric:tabular-nums; color:var(--ink2); }
.factor-head .pts{ margin-left:auto; font-family:'IBM Plex Mono',monospace;
  font-variant-numeric:tabular-nums; color:var(--muted); }
.factor .bar{ display:block; height:6px; margin:.35rem 0 .3rem; background:var(--surface-3); border-radius:3px; overflow:hidden; }
.factor .bar span{ display:block; height:100%; background:var(--accent); border-radius:3px;
  transform-origin:left; animation:ti-grow-x 420ms var(--ease) both; }
.factor .why{ font-size:.78rem; color:var(--ink2); line-height:1.6; }

.model-note{ font-size:.82rem; color:var(--ink2); line-height:1.6; margin-top:1rem;
  border-top:1px solid var(--line); padding-top:.7rem; }
.model-note b{ color:var(--ink); }
.caveat-inline{ font-size:.74rem; color:var(--muted); }

.actions{ margin-top:1rem; border-top:1px solid var(--line); padding-top:.7rem; }
.actions-title{ font-size:.85rem; font-weight:600; color:var(--ink); margin:0 0 .5rem; }
.actions ol{ margin:0; padding:0; list-style:none; counter-reset:step; }
.actions li{ display:grid; grid-template-columns:5.6rem 1fr; gap:.2rem .8rem; padding:.5rem 0;
  border-bottom:1px solid var(--line); }
.actions li:last-child{ border-bottom:none; }
.actions .urgency{ grid-row:span 2; align-self:start; display:inline-flex; align-items:center; gap:6px;
  font-size:.74rem; color:var(--ink2); }
.actions .urgency::before{ content:""; width:8px; height:8px; border-radius:2px; background:var(--u); flex:none; }
.actions .step{ font-size:.85rem; color:var(--ink); }
.actions .detail{ font-size:.78rem; color:var(--ink2); line-height:1.6; }

/* Escalation queue */
.queue-row{ display:flex; align-items:center; gap:.6rem; padding:.55rem .5rem; margin:0 -.5rem;
  border-radius:var(--radius); font-size:.84rem; transition:background-color var(--dur) var(--ease); }
.queue-row:hover{ background:var(--surface-2); }
.queue-row .mark{ width:8px; height:8px; border-radius:2px; flex:none; }
.queue-row .t{ color:var(--ink); }
.queue-row .id{ color:var(--ink2); font-size:.78rem; }
.queue-row .w{ margin-left:auto; color:var(--ink2); font-size:.78rem; }
.queue-row .w b{ font-family:'IBM Plex Mono',monospace; font-variant-numeric:tabular-nums; color:var(--ink); }

@media (prefers-reduced-motion: reduce){
  *,*::before,*::after{ animation-duration:.01ms !important; transition-duration:.01ms !important; }
}
</style>
"""


# ---------------------------------------------------------------- helpers --

def _section_header(text: str):
    st.markdown(f'<div class="sec-hdr">{text}</div>', unsafe_allow_html=True)


def _format_satellites(value) -> str:
    """satellites is a real list on a fresh pipeline run, but comes back as a
    Python-list-repr string after a round-trip through the cluster_summary
    CSV cache, so handle both without erroring."""
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
    """Label in normal text colour with a small colour marker. Colour carries
    the state; the words stay readable, and the marker is never the only cue
    because the text always names the state."""
    return f'<span class="pill"><i class="mark" style="background:{color}"></i>{text}</span>'


def _stat_row(cells: list[tuple]):
    """Each cell is (label, value, ...). Trailing flag/icon/accent members from
    the earlier design are accepted and ignored: the metric strip carries no
    icons and no colour, so a number never has to be decoded."""
    parts = []
    for cell in cells:
        label, value = cell[0], cell[1]
        parts.append(f'<div class="stat"><div class="lbl">{label}</div><div class="val">{value}</div></div>')
    st.markdown('<div class="statrow">' + "".join(parts) + "</div>", unsafe_allow_html=True)


def _style_fig(fig: go.Figure, height: int = 320) -> go.Figure:
    """Plotly never sees the page stylesheet, so every chart is set on the same
    surface with the same recessive grid and text tokens as the rest of the UI."""
    fig.update_traces(marker_cornerradius=4, selector=dict(type="bar"))
    fig.update_layout(
        bargap=0.3, height=height, margin=dict(l=8, r=8, t=8, b=8),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE, showlegend=False,
        font=dict(family="IBM Plex Sans, system-ui, sans-serif", size=12, color=INK2),
        hoverlabel=dict(bgcolor=SURFACE_2, bordercolor=LINE,
                        font=dict(family="IBM Plex Sans, system-ui, sans-serif", size=12, color=INK)),
        xaxis=dict(gridcolor=LINE, zerolinecolor=LINE, linecolor=LINE, tickcolor=LINE, tickfont=dict(color=MUTED)),
        yaxis=dict(gridcolor=LINE, zerolinecolor=LINE, linecolor=LINE, tickcolor=LINE, tickfont=dict(color=MUTED)),
        # Bars/lines tween to their new values on a filter change instead of a
        # hard cut. Only takes effect when st.plotly_chart keeps the same
        # `key` across the rerun, since Plotly's transition compares against
        # the chart already on screen, not a description of "how to arrive."
        transition=dict(duration=250, easing="cubic-in-out"),
    )
    return fig


@st.cache_data(ttl=30, show_spinner=False)
def _holo_app_reachable(url: str) -> bool:
    """Whether the holo-view-maker app answers at `url`. The 3D page opens on
    that GPU-rendered MapLibre globe when it is running, and falls back to the
    self-contained embedded globe when it is not."""
    try:
        with urllib.request.urlopen(url, timeout=0.5) as resp:
            return resp.status < 500
    except Exception:
        return False


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


def _auto_dispatch(alerts: list[dict]) -> None:
    """Send the critical alerts this run produced, and start each one's
    acknowledgement clock so the Alerts page can escalate it later."""
    if not alerts or not st.session_state.get("alert_auto_dispatch", config.ALERT_AUTO_DISPATCH_CRITICAL):
        return
    from src.alerts import escalation
    from src.alerts import messages as alert_messages

    phone = st.session_state.get("alert_phone", config.ALERT_RECIPIENT_PHONE)
    results = alert_messages.send_batch_critical_alerts(alerts, phone=phone)
    if not results:
        return
    by_id = {str(a.get("event_id") or a.get("grid_cell")): a for a in alerts}
    for res in results:
        source = by_id.get(str(res.get("event_id"))) or res
        escalation.record_dispatch(source, phone, channel=res.get("channel", "message"))
    st.toast(f"{len(results)} critical alert(s) dispatched to {phone}.", icon=":material/sms:")


def run_and_cache(api_key: str | None = None):
    with st.spinner("Running pipeline: fetch, clean, geospatial join, classify, risk, alerts..."):
        try:
            info = pipeline.run_pipeline(api_key=api_key)
        except Exception as exc:
            st.error(f"Pipeline run failed: {exc}", icon=":material/cancel:")
            return
    st.session_state["run_info"] = {k: v for k, v in info.items() if k not in ("detail_gdf", "cluster_df")}
    st.session_state["run_info"]["n_alerts"] = len(info["alerts"])
    _shared_runs()["regional"] = st.session_state["run_info"]
    _load_cached_detail.clear()
    _load_cached_clusters.clear()
    _load_cached_alerts.clear()

    _auto_dispatch(info["alerts"])

    # The globe is exported from the same run, so both views agree.
    try:
        exported_3d = export_pipeline_events_for_holo_view(info.get("detail_gdf"), info.get("cluster_df"))
        st.session_state["holo_events_count"] = len(exported_3d)
        st.session_state["holo_last_synced"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    except Exception as exc:
        print(f"[app] 3D globe export error: {exc}")

    st.success(f"Done. {len(info['detail_gdf'])} detections, {len(info['cluster_df'])} clusters, "
               f"{len(info['alerts'])} alerts. The 3D globe was updated from the same run.",
               icon=":material/check_circle:")


def recompute_risk_and_cache(weights: dict):
    """Re-score already-loaded detail/cluster data with custom risk
    weights, with no re-fetch, re-geospatial-join, or re-training needed, only
    risk_score/risk_level/status/alerts are recomputed and re-cached."""
    from src.alerts import engine as alert_engine
    from src.risk import scoring as risk_scoring
    from src.utils import status as status_utils

    gdf = _load_cached_detail()
    cluster_df = _load_cached_clusters()
    if gdf is None or gdf.empty:
        st.warning("No data loaded yet. Run the pipeline first.", icon=":material/warning:")
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

    _auto_dispatch(alerts)

    # The globe is exported from the same run, so both views agree.
    try:
        exported_3d = export_pipeline_events_for_holo_view(gdf, cluster_df)
        st.session_state["holo_events_count"] = len(exported_3d)
        st.session_state["holo_last_synced"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    except Exception as exc:
        print(f"[app] 3D globe export error: {exc}")

    st.success(f"Risk scores recomputed. {len(alerts)} alerts regenerated and the 3D globe updated.",
               icon=":material/check_circle:")


@st.cache_resource(show_spinner=False)
def _national_snapshot(mtime: float) -> dict | None:
    """Latest live national run from disk, read once per file version (the
    mtime key) and shared by every session, never recomputed on page load."""
    from src.national import snapshot
    return snapshot.load()


def _run_time(info: dict | None) -> pd.Timestamp:
    at = (info or {}).get("run_at")
    return pd.Timestamp(at) if at is not None else pd.Timestamp.min


def _adopt_latest_national_run() -> None:
    """Use the saved live run (written by Run Pipeline or
    scripts/refresh_national_globe.py) whenever it is newer than what this
    server or session already holds."""
    from src.national import snapshot
    mtime = snapshot.mtime()
    if mtime is None:
        return
    snap = _national_snapshot(mtime)
    if not snap:
        return
    shared = _shared_runs()
    if _run_time(shared.get("national")) < _run_time(snap):
        shared["national"] = snap
    if _run_time(st.session_state.get("national_info")) < _run_time(snap):
        st.session_state["national_info"] = snap


def run_national_and_cache(api_key: str | None = None):
    from src.national.pipeline import run_national_pipeline
    with st.spinner("Running national pipeline: fetch, clean, grid, state tagging, risk..."):
        try:
            info = run_national_pipeline(api_key=api_key)
        except Exception as exc:
            st.error(f"National pipeline run failed: {exc}", icon=":material/cancel:")
            return
    info["run_at"] = pd.Timestamp.now()
    st.session_state["national_info"] = info
    _shared_runs()["national"] = info
    _auto_dispatch(_derive_national_alerts(info.get("events_df")))

    # The globe is exported from the same run, so both views agree.
    try:
        exported_3d = export_pipeline_events_for_holo_view(
            events_df=info.get("events_df"),
            national_detail_df=info.get("detail_df"),
        )
        st.session_state["holo_events_count"] = len(exported_3d)
        st.session_state["holo_last_synced"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    except Exception as exc:
        print(f"[app] 3D globe national export error: {exc}")

    st.success(f"Done. {info['n_observations']} observations, {info['n_events']} events across "
               f"{info['state_summary']['state'].notna().sum() if not info['state_summary'].empty else 0} states. "
               "The 3D globe was updated from the same run.",
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
.thermal-cluster-icon {{ background: transparent !important; border: none !important; }}
.thermal-cluster-inner {{
    width:100%; height:100%; display:flex; align-items:center; justify-content:center;
    background:{SURFACE}; border:1px solid {ACCENT}; border-radius:50%; color:{INK};
    font-family:{MONO_STACK}; font-weight:500; font-size:12px; font-variant-numeric:tabular-nums;
}}
.leaflet-popup-content-wrapper {{ background:{SURFACE} !important; color:{INK} !important;
    border-radius:6px !important; border:1px solid {LINE} !important; box-shadow:none !important; }}
.leaflet-popup-tip {{ background:{SURFACE} !important; }}
.leaflet-control-layers, .leaflet-bar a {{ background:{SURFACE} !important; color:{INK} !important;
    border-color:{LINE} !important; }}
.leaflet-control-layers-toggle {{ filter:invert(1) brightness(1.5); }}
.leaflet-control-scale-line {{ background:{SURFACE_2} !important; color:{INK} !important;
    border-color:{LINE} !important; font-family:{MONO_STACK}; }}
</style>
"""


ESRI_TILES = "https://server.arcgisonline.com/ArcGIS/rest/services/{service}/MapServer/tile/{{z}}/{{y}}/{{x}}"
ESRI_ATTR = "Esri, HERE, Garmin, © OpenStreetMap contributors"


def _add_base_layers(m: folium.Map):
    """Esri's free canvas tiles, not CARTO's raster ones: CARTO now stamps
    "API KEY REQUIRED" across keyless raster tiles. (The 3D globe still uses
    CARTO's GL vector style, which is keyless and unwatermarked.)

    Dark is added last so it is the one showing: folium stacks tile layers in
    the order they are added, and a later layer covers the ones before it."""
    folium.TileLayer(
        tiles=ESRI_TILES.format(service="World_Imagery"),
        attr="Esri, Maxar, Earthstar Geographics", name="Satellite imagery", control=True,
    ).add_to(m)
    folium.TileLayer(
        tiles=ESRI_TILES.format(service="Canvas/World_Light_Gray_Base"),
        attr=ESRI_ATTR, name="Light", control=True,
    ).add_to(m)
    folium.TileLayer(
        tiles=ESRI_TILES.format(service="Canvas/World_Dark_Gray_Base"),
        attr=ESRI_ATTR, name="Dark", control=True,
    ).add_to(m)


def _add_map_chrome(m: folium.Map, legend_html: str | None = None):
    """Shared premium-map furniture: matching cluster icons/popups, a
    fullscreen control, a base-layer switcher, and (optionally) a legend,
    kept minimal per the "large map, minimal controls" design goal."""
    m.get_root().html.add_child(folium.Element(MAP_CHROME_CSS))  # pyright: ignore[reportAttributeAccessIssue]
    Fullscreen(position="topright").add_to(m)
    folium.LayerControl(position="topright", collapsed=True).add_to(m)
    if legend_html:
        m.get_root().html.add_child(folium.Element(legend_html))  # pyright: ignore[reportAttributeAccessIssue]


def _legend_html(title: str, items: dict[str, str]) -> str:
    chips = "".join(
        f'<span style="display:inline-flex;align-items:center;gap:6px;font-size:12px;margin:3px 10px 3px 0;'
        f'color:{INK2};"><i style="width:9px;height:9px;border-radius:2px;display:inline-block;flex:none;'
        f'background:{c}"></i>{label.capitalize()}</span>'
        for label, c in items.items()
    )
    return f"""
    <div style="position:fixed;bottom:58px;left:26px;z-index:9999;background:{SURFACE};
        padding:10px 14px;border-radius:6px;border:1px solid {LINE};
        font-family:{FONT_STACK};max-width:240px;">
        <b style="color:{INK};font-size:12px;font-weight:600;">{title}</b><br>{chips}
    </div>"""


def build_map(gdf: gpd.GeoDataFrame, label_field: str, color_by: str) -> folium.Map:
    center_lat = (config.BBOX["min_lat"] + config.BBOX["max_lat"]) / 2
    center_lon = (config.BBOX["min_lon"] + config.BBOX["max_lon"]) / 2
    m = folium.Map(location=[center_lat, center_lon], zoom_start=8, tiles=None, control_scale=True)
    _add_base_layers(m)

    folium.Rectangle(
        bounds=[[config.BBOX["min_lat"], config.BBOX["min_lon"]], [config.BBOX["max_lat"], config.BBOX["max_lon"]]],
        color="#5cb8dc", weight=1, fill=False, dash_array="4", tooltip="Target region bounding box",
    ).add_to(m)

    cluster = MarkerCluster(disableClusteringAtZoom=12, maxClusterRadius=45,
                             icon_create_function=CLUSTER_ICON_JS).add_to(m)

    for _, row in gdf.iterrows():
        if color_by == "risk":
            color = RISK_COLORS.get(row.get("risk_level", ""), "#71808f")
        else:
            color = CATEGORY_COLORS.get(row[label_field], "#71808f")

        risk_pct = max(0, min(100, row.get("risk_score", 0)))
        popup_html = (
            f'<div style="font-family:{FONT_STACK};font-size:12.5px;line-height:1.6;padding:2px;min-width:200px;">'
            f"<b style='color:{color}'>{row[label_field]}</b><br>"
            f"<span style='color:#a1adba;'>Risk {row.get('risk_score', 0):.0f}/100 ({row.get('risk_level', '?')})</span>"
            f'<div style="height:4px;background:rgba(255,255,255,.1);border-radius:2px;margin:.3rem 0 .5rem;">'
            f'<div style="height:100%;width:{risk_pct}%;background:{RISK_COLORS.get(row.get("risk_level", ""), "#71808f")};border-radius:2px;"></div></div>'
            f"Date: {row['acq_date']} ({row.get('daynight', '?')})<br>"
            f"FRP: {row['frp']:.1f} MW &middot; Confidence: {row['confidence_numeric']:.0f}<br>"
            f"Persistence: {row['persistence_days']} days &middot; Zone: {row['zone_type']}<br>"
            f"<span style='font-family:{MONO_STACK};color:#71808f;font-size:11px;'>{row.get('grid_cell', '?')}</span>"
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
    legend_title = "Classification" if color_by != "risk" else "Risk level"
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
                    "fillColor": CATEGORY_COLORS.get(row[label_field], "#71808f"),
                    "color": CATEGORY_COLORS.get(row[label_field], "#71808f"),
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
    color = CATEGORY_COLORS.get(label, "#71808f")
    risk = cluster_row.get("risk_score", 0)
    risk_lvl = cluster_row.get("risk_level", "LOW")
    status = cluster_row.get("status", "")

    event_id = cluster_row.get("event_id", cluster_row["grid_cell"])
    st.markdown(f"#### Thermal event `{event_id}`", unsafe_allow_html=False)
    st.caption(f"Grid cell {cluster_row['grid_cell']}")
    top1, top2, top3, top4 = st.columns(4)
    top1.markdown(_pill(label, color), unsafe_allow_html=True)
    top2.markdown(_pill(f"RISK {risk:.0f}/100", RISK_COLORS.get(risk_lvl, "#71808f")), unsafe_allow_html=True)
    top3.markdown(_pill(risk_lvl, RISK_COLORS.get(risk_lvl, "#71808f")), unsafe_allow_html=True)
    top4.markdown(_pill(status, STATUS_COLORS.get(status, "#71808f")), unsafe_allow_html=True)
    if bool(cluster_row.get("is_anomalous")):
        st.markdown(_pill("THERMAL ANOMALY DETECTED", "#d03b3b", icon="warning"), unsafe_allow_html=True)

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
                       else f"ML model instead predicts: **{ml_label}** (model confidence {ml_conf:.0%}), worth a second look")

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
        wc3.markdown(f'<div class="stat"><div class="lbl">Change</div><div class="val" style="color:{"#d03b3b" if change_pct>0 else "var(--ink)"}">{arrow} {abs(change_pct):.0f}%</div></div>', unsafe_allow_html=True)
        if bool(cluster_row.get("is_anomalous")):
            st.caption(f"Flagged anomalous: latest detection is {zscore:.1f} standard deviations above this "
                       f"cell's own historical baseline. The thresholds are {2.0:.0f} standard deviations and "
                       f"{2.0:.0f} times baseline FRP, "
                       "both an operational prototype threshold, not a scientific standard).")
        else:
            st.caption("Within this cell's own normal historical range, so not flagged as anomalous.")
    else:
        st.caption("What changed: not enough detection history at this location yet to establish a baseline.")

    if not detail_rows.empty:
        st.markdown("**Historical Activity**")
        hist = detail_rows.sort_values("acq_date")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=hist["acq_date"], y=hist["frp"], mode="lines+markers",
                                  line=dict(color=color, width=2), marker=dict(size=6), name="FRP (MW)"))
        _style_fig(fig, height=220)
        fig.update_layout(yaxis=dict(title="FRP (MW)", gridcolor=LINE))
        st.plotly_chart(fig, width="stretch", key=f"chart_frp_history_{cluster_row['grid_cell']}")

        st.markdown("**Recent Observations**")
        st.dataframe(
            hist[["acq_date", "frp", "confidence_numeric", "satellite", "daynight"]].sort_values("acq_date", ascending=False).head(10),
            width="stretch", hide_index=True,
        )

    if analyst_mode:
        with st.expander("Analyst view: raw feature values"):
            feature_cols = ["frp", "brightness", "confidence_numeric", "persistence_days", "detection_count",
                             "avg_frp", "max_frp", "frp_trend", "industrial_distance_km", "mine_distance_km",
                             "recurrence_frequency"]
            present = [c for c in feature_cols if c in detail_rows.columns]
            st.dataframe(detail_rows[present].tail(1), width="stretch", hide_index=True)
            st.caption(f"grid_cell={cluster_row['grid_cell']} · zone_type={cluster_row.get('zone_type')}")

    existing_review = store.load_reviews(region="jharkhand_odisha")
    existing_review = existing_review[existing_review["event_id"] == event_id] if not existing_review.empty else existing_review
    b1, b2 = st.columns(2)
    if b1.button("Mark reviewed", key=f"review_btn_{cluster_row['grid_cell']}", width="stretch"):
        store.save_review(event_id, cluster_row["grid_cell"], "jharkhand_odisha", "Reviewed")
        st.toast("Marked reviewed.", icon=":material/check_circle:")
        st.rerun()
    if not existing_review.empty:
        b1.caption(f"Recorded: {existing_review.iloc[0]['decision']}")
    b2.button("Open 3D globe", key=f"inv_jump_3d_{cluster_row['grid_cell']}", width="stretch", icon=":material/public:",
              help="Inspect this thermal event on the 3D globe",
              on_click=_navigate(page="3D Globe"))


    r1, r2 = st.columns(2)
    report_text = _build_incident_report(cluster_row, detail_rows)
    r1.download_button("Report (text)", report_text, f"incident_{cluster_row['grid_cell']}.txt", "text/plain",
                        key=f"report_btn_{cluster_row['grid_cell']}", width="stretch")
    report_html = _build_incident_report_html(cluster_row, detail_rows)
    r2.download_button("Report (HTML, print to PDF)", report_html, f"incident_{cluster_row['grid_cell']}.html",
                        "text/html", key=f"report_html_btn_{cluster_row['grid_cell']}", width="stretch")


def _build_incident_report(cluster_row: pd.Series, detail_rows: pd.DataFrame) -> str:
    window_col = f"persistence_{config.PERSISTENCE_DEFAULT_WINDOW_DAYS}d"
    lines = [
        "INCIDENT REPORT: AI-assisted early-warning platform (SIH26162)",
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
            f"{cluster_row.get('latest_frp', 0):.1f} MW ({cluster_row.get('frp_change_pct', 0):+.0f}%), "
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
    """A styled, standalone HTML report with no external assets, so it opens
    correctly offline and can be turned into a PDF via the browser's own
    Print dialog without adding a PDF-generation dependency to the project."""
    window_col = f"persistence_{config.PERSISTENCE_DEFAULT_WINDOW_DAYS}d"
    label = cluster_row.get("dominant_label", "Requires Verification")
    color = CATEGORY_COLORS.get(label, "#71808f")
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
        anomaly_html = '<b style="color:#d03b3b">ANOMALOUS</b>' if cluster_row.get("is_anomalous") else "within normal range"
        rows.append(_row(
            "What Changed",
            f"{cluster_row.get('frp_baseline_mean', 0):.1f} MW &rarr; {cluster_row.get('latest_frp', 0):.1f} MW "
            f"({cluster_row.get('frp_change_pct', 0):+.0f}%), {anomaly_html}"
        ))

    evidence_items = ""
    if not detail_rows.empty:
        for item in str(detail_rows.iloc[-1].get("rule_evidence", "")).split("|"):
            if item.strip():
                evidence_items += f"<li>{item.strip()}</li>"

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Incident report {cluster_row.get('event_id', cluster_row["grid_cell"])}</title>
<style>
body{{font-family:'IBM Plex Sans',system-ui,-apple-system,'Segoe UI',sans-serif;background:#0a0e13;color:#e4eaf0;
  max-width:720px;margin:2rem auto;padding:0 1.5rem;}}
h1{{font-size:1.3rem;margin-bottom:.1rem;}}
.eyebrow{{font-family:monospace;font-size:.72rem;letter-spacing:.08em;text-transform:uppercase;color:#5cb8dc;}}
.disclaimer{{font-size:.82rem;color:#a1adba;border-left:3px solid #5cb8dc;padding:.4rem .8rem;margin:1rem 0;background:#10161d;}}
.pill{{display:inline-block;font-family:monospace;font-size:.75rem;font-weight:600;padding:.2rem .6rem;border-radius:99px;
  color:{color};background:{color}22;border:1px solid {color}55;margin-right:.4rem;}}
table{{width:100%;border-collapse:collapse;margin:1rem 0;font-size:.85rem;}}
td{{padding:.4rem .6rem;border-bottom:1px solid rgba(255,255,255,.08);}}
td.k{{color:#a1adba;width:40%;}}
td.v{{font-family:monospace;}}
h2{{font-size:.95rem;border-bottom:1px solid rgba(255,255,255,.16);padding-bottom:.3rem;margin-top:1.5rem;}}
ul{{font-size:.85rem;line-height:1.7;}}
.footer{{font-size:.72rem;color:#71808f;margin-top:2rem;border-top:1px dashed rgba(255,255,255,.08);padding-top:.6rem;}}
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

NAV_PAGES = ["Overview", "Live Map", "3D Globe", "Events", "Alerts", "Cameras", "Analytics",
             "Investigations", "Settings"]
NAV_ICONS = {
    "Overview": "space_dashboard", "Live Map": "map", "3D Globe": "public",
    "Events": "flare", "Alerts": "notifications_active", "Cameras": "videocam",
    "Analytics": "monitoring", "Investigations": "manage_search", "Settings": "settings",
}


# One label for the belt region, so the selector, the session key and every
# caption spell it the same way.
BELT_LABEL = "Jharkhand and Odisha belt"


def _navigate(page: str | None = None, region: str | None = None, selected_cell: str | None = None):
    """Returns an on_click callback that changes page/region/selected_cell.
    Must be wired via `st.button(..., on_click=_navigate(...))`, NOT called
    inside an `if st.button(...):` block. The sidebar nav buttons/topbar_region
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
            st.session_state["topbar_region"] = "India" if region == "india" else BELT_LABEL
    return _cb


def _render_sidebar_nav() -> str:
    with st.sidebar:
        st.markdown('<div class="brand">Thermal Intelligence</div>'
                     '<div class="brand-sub">Satellite thermal monitoring for India</div>', unsafe_allow_html=True)
        st.write("")
        page = st.session_state.get("page", "Overview")
        for p in NAV_PAGES:
            st.button(
                p, key=f"navbtn_{p}", icon=f":material/{NAV_ICONS[p]}:",
                type="primary" if p == page else "secondary",
                width="stretch", on_click=_navigate(page=p),
            )
        st.divider()
        st.caption("Pipeline runs and thresholds live on the Settings page. Data is live NASA FIRMS only.")
    return page


def _derive_national_alerts(events_df: pd.DataFrame) -> list[dict]:
    """No national alert-engine run exists (no rule-based classification runs
    country-wide). These are computed on the fly from real classified event
    rows, not a separate stored/fabricated alert feed."""
    if events_df is None or events_df.empty:
        return []
    sev = events_df[events_df["risk_level"].isin(["HIGH", "CRITICAL"])].sort_values("risk_score", ascending=False)
    alerts = []
    for _, r in sev.iterrows():
        alerts.append({
            "title": f"{r.get('risk_level').title()} thermal activity in {r.get('state') or 'an untagged area'}",
            "event_id": r.get("event_id", r.get("grid_cell")), "grid_cell": r.get("grid_cell"),
            "latitude": r.get("latitude", 0.0), "longitude": r.get("longitude", 0.0),
            "classification": r.get("category") or ("Persistent source" if r.get("is_persistent") else "Thermal event"),
            "risk_score": r.get("risk_score", 0), "persistence_days": r.get("persistence_days", 0),
            "frp": r.get("max_frp", r.get("avg_frp", 0.0)),
            "status": r.get("risk_level"), "severity": r.get("risk_level"),
            # The risk model's answer travels with the alert, so the analyst
            # deciding whether to dispatch sees why and what to do in one place.
            "priority": r.get("priority"),
            "risk_summary": r.get("risk_summary"),
            "risk_factors": r.get("risk_factors") if isinstance(r.get("risk_factors"), list) else [],
            "actions": r.get("actions") if isinstance(r.get("actions"), list) else [],
            "model_check": r.get("model_check") if isinstance(r.get("model_check"), dict) else None,
            "facility": r.get("facility") if isinstance(r.get("facility"), dict) else None,
            "reasons": r.get("reasons") if isinstance(r.get("reasons"), list) else [],
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
        st.caption(f"{len(matches)} matches. Refine them on the Events page." if not matches.empty else f"No match for '{query}'.")


SOURCE_LABELS = {
    "firms_live": "Live NASA FIRMS",
    "local_cache": "Stored live history",
    "overpass_live": "Live OpenStreetMap",
}


def _render_topbar():
    region = st.session_state["region"]

    if region == "india":
        info = st.session_state.get("national_info")
        run_info = info
        alerts = _derive_national_alerts(info["events_df"]) if info else []
    else:
        run_info = st.session_state.get("run_info")
        alerts = _load_cached_alerts()

    source_key = (run_info or {}).get("hotspot_source")
    src = SOURCE_LABELS.get(source_key, "Not run yet")
    run_at = (run_info or {}).get("run_at")

    # The belt's results live in files, so a session that did not run the
    # pipeline itself still reports the run those files came from rather than
    # claiming nothing has ever run.
    if run_at is None and region != "india":
        saved = config.PROCESSED_DIR / "cluster_summary.csv"
        if saved.exists():
            run_at = pd.Timestamp.fromtimestamp(saved.stat().st_mtime)
            src = "Stored live run"

    n_critical = sum(1 for a in alerts if a.get("severity") == "CRITICAL")
    updated = pd.Timestamp(run_at).strftime("%Y-%m-%d %H:%M") if run_at is not None else "never"

    c1, c2, c3, c4, c5 = st.columns([2.9, 1.7, 1.5, 1.9, 1.1])
    with c1:
        st.markdown(
            '<div class="topbar-brand"><h1>Thermal Intelligence</h1>'
            '<p class="sub">Satellite thermal monitoring and industrial risk analysis for India.</p></div>',
            unsafe_allow_html=True,
        )
    with c2:
        # Same rationale as nav_radio above: no `index=` once topbar_region
        # can also be set programmatically via a callback (_navigate).
        st.session_state.setdefault("topbar_region", "India" if region == "india" else BELT_LABEL)
        region_label = st.selectbox("Region", ["India", BELT_LABEL], key="topbar_region")
        new_region = "india" if region_label == "India" else "jharkhand_odisha"
        if new_region != region:
            st.session_state["region"] = new_region
            st.rerun()
    with c3:
        st.markdown(f'<div class="topbar-meta">{src}<br>Updated <span class="v">{updated}</span></div>',
                     unsafe_allow_html=True)
    with c4:
        query = st.text_input("Search", placeholder="Search event ID, state, grid cell",
                               label_visibility="collapsed", key="global_search")
        if query:
            _handle_global_search(query, region)
    with c5:
        st.button(f"Alerts ({n_critical})", key="topbar_alerts_btn", width="stretch",
                  icon=":material/notifications_active:", on_click=_navigate(page="Alerts"))
    st.markdown('<hr class="topbar-rule">', unsafe_allow_html=True)


# ------------------------------------------------------------------ main --

def main():
    st.session_state.setdefault("analyst_mode", False)
    st.session_state.setdefault("selected_cell", None)
    st.session_state.setdefault("region", config.DEFAULT_REGION)
    st.session_state.setdefault("page", "Overview")
    st.session_state.setdefault("alert_phone", config.ALERT_RECIPIENT_PHONE)
    st.session_state.setdefault("alert_auto_dispatch", config.ALERT_AUTO_DISPATCH_CRITICAL)
    st.session_state.setdefault("escalate_after_min", config.ALERT_ESCALATE_AFTER_MIN)
    st.session_state.setdefault("auto_escalate_call", config.ALERT_AUTO_ESCALATE_CALL)

    # The latest live national run on disk, the same run the 3D globe was
    # exported from, so the dashboard never shows data the globe does not.
    _adopt_latest_national_run()

    # Adopt a run completed by any earlier session, so opening a new tab shows
    # the existing results immediately instead of an empty "not yet run" state.
    shared = _shared_runs()
    for shared_key, session_key in (("national", "national_info"), ("regional", "run_info")):
        if session_key not in st.session_state and shared_key in shared:
            st.session_state[session_key] = shared[shared_key]

    st.markdown(CSS, unsafe_allow_html=True)

    _render_sidebar_nav()
    _render_topbar()

    region = st.session_state["region"]
    page = st.session_state["page"]

    if region == "india":
        _route_national_page(page)
    else:
        _route_regional_page(page)


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
        # Eight classification hues exceed what a scatter can be read by, so
        # risk (four ordered states) is the default map colouring.
        "flt_color": "risk",
        "flt_onlyp": False,
        "flt_onlyc": False,
    }

    if show_ui:
        with st.container(border=True):
            _section_header("Filters")
            f1, f2, f3, f4 = st.columns(4)
            date_range = f1.slider("Date range", min_value=min_date, max_value=max_date,
                                    value=(min_date, max_date), key="flt_date") if min_date != max_date else (min_date, max_date)
            classifications = f2.multiselect("Classification", list(CATEGORY_COLORS.keys()),
                                              default=list(CATEGORY_COLORS.keys()), key="flt_cls")
            risk_levels = f3.multiselect("Risk level", list(RISK_COLORS.keys()),
                                          default=list(RISK_COLORS.keys()), key="flt_risk")
            label_field = f4.radio("Label source", ["rule_label", "ml_label"], horizontal=True, key="flt_label")

            g1, g2, g3, g4 = st.columns(4)
            min_conf = g1.slider("Minimum confidence", 0, 100, 0, key="flt_conf")
            min_persist = g2.slider("Minimum persistence (days)", 0, int(gdf["persistence_days"].max()) or 1, 0, key="flt_pers")
            frp_range = g3.slider("FRP range (MW)", 0.0, max(frp_max_val, 1.0), (0.0, max(frp_max_val, 1.0)), key="flt_frp")
            color_by = g4.radio("Colour map by", ["risk", "classification"], horizontal=True, key="flt_color")

            h1, h2, h3 = st.columns([1, 1, 2])
            only_persistent = h1.checkbox("Only persistent", key="flt_onlyp")
            only_critical = h2.checkbox("Only critical risk", key="flt_onlyc")
            if h3.button("Reset Filters", key="flt_reset"):
                for k in defaults:
                    st.session_state.pop(k, None)
                st.rerun()
    else:
        # No filter UI on this page, so fall back to the last values chosen on the
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


# Explanation first, coordinates last: the point of the national table is why a
# hotspot is there, so the columns that answer that lead, in this order.
EVENT_COLUMN_LABELS = {
    "event_id": "Event",
    "state": "State",
    "district": "District",
    "place": "Nearest place",
    "category": "Category",
    "risk_level": "Risk",
    "risk_score": "Risk score",
    "max_frp": "Peak FRP (MW)",
    "persistence_days": "Days active",
    "observation_count": "Detections",
    "corroborated": "Corroborated",
    "facility": "Nearest facility",
    "reasons": "Why it is here",
    "latitude": "Latitude",
    "longitude": "Longitude",
    "grid_cell": "Grid cell",
}


def _readable_event_columns(df: pd.DataFrame) -> pd.DataFrame:
    """National events carry structured open-source context (a facility dict, a
    reasons list, an evidence dict) for the 3D globe. Flatten it to text so the
    table and its CSV export read as the explanation itself."""
    table = df.copy()
    if {"place_name", "place_km", "place_dir"} <= set(table.columns):
        table["place"] = [
            f"{d} {k:.0f} km of {n}" if isinstance(n, str) and pd.notna(k) and k >= 1
            else (n if isinstance(n, str) else "")
            for n, k, d in zip(table["place_name"], table["place_km"], table["place_dir"])
        ]
    if "facility" in table.columns:
        table["facility"] = table["facility"].map(
            lambda f: f"{f.get('name') or 'unnamed'}: {f.get('kind')}, {f.get('distanceKm')} km ({f.get('source')})"
            if isinstance(f, dict) else ""
        )
    if "reasons" in table.columns:
        table["reasons"] = table["reasons"].map(
            lambda r: " ".join(r) if isinstance(r, (list, tuple)) else ""
        )
    ordered = [c for c in EVENT_COLUMN_LABELS if c in table.columns]
    rest = [c for c in table.columns
            if c not in ordered and c not in ("evidence", "place_name", "place_km", "place_dir")]
    return table[ordered + rest].rename(columns=EVENT_COLUMN_LABELS)


def _render_events_table(df: pd.DataFrame, region_key: str):
    with st.container(border=True):
        _section_header(f"Events: {len(df):,} rows")
        if df.empty:
            st.info("No events match the current filters.", icon=":material/search_off:")
            return
        search = st.text_input("Search grid cell / state / classification", key=f"events_search_{region_key}")
        table = _readable_event_columns(df)
        if search:
            m = table.astype(str).apply(lambda col: col.str.contains(search, case=False, na=False)).any(axis=1)
            table = table[m]
        st.dataframe(table, hide_index=True, width="stretch")
        st.download_button("Export CSV", table.to_csv(index=False), f"events_{region_key}.csv", "text/csv",
                            key=f"events_export_{region_key}")




# The one fixed payload in the app: a dispatch test needs a message to send,
# and it is labelled as a test everywhere it appears.
TEST_ALERT_EVENT = {
    "event_id": "TH-TEST-CRIT",
    "latitude": 22.8046, "longitude": 86.1850,
    "risk_score": 88.5, "risk_level": "CRITICAL", "severity": "CRITICAL",
    "classification": "Likely Industrial Fire",
    "ai_confidence": 94.2, "frp": 16.5, "persistence_days": 24,
    "industrial_distance_km": 0.15, "status": "Test dispatch, not a real detection.",
}


def _render_alert_gateway_settings(suffix: str):
    """Where critical alerts are sent. Shared by both regions so the recipient
    and the channel credentials are configured in exactly one place."""
    with st.container(border=True):
        _section_header("Critical alert dispatch")
        st.caption("Where an alert goes when an event crosses the critical threshold. With no channel "
                   "credentials configured, dispatches are simulated and written to the local log.")

        msg1, msg2 = st.columns(2)
        with msg1:
            phone = st.text_input(
                "Recipient phone number",
                value=st.session_state.get("alert_phone", config.ALERT_RECIPIENT_PHONE),
                key=f"alert_settings_phone_{suffix}",
                help="Country code or 10 digits.",
            )
            st.session_state["alert_phone"] = phone
        with msg2:
            st.session_state["alert_auto_dispatch"] = st.toggle(
                "Dispatch critical alerts automatically",
                value=st.session_state.get("alert_auto_dispatch", config.ALERT_AUTO_DISPATCH_CRITICAL),
                key=f"alert_settings_auto_{suffix}",
                help=f"Send without asking whenever an event scores {config.ALERT_CRITICAL_RISK_MIN} or above.",
            )

        with st.expander("Channel credentials"):
            st.caption("Optional. Twilio, Telegram and a plain webhook are supported.")
            creds = dict(
                twilio_sid=st.text_input("Twilio account SID", value=config.TWILIO_ACCOUNT_SID,
                                         type="password", key=f"msg_t_sid_{suffix}") or None,
                twilio_token=st.text_input("Twilio auth token", value=config.TWILIO_AUTH_TOKEN,
                                           type="password", key=f"msg_t_tok_{suffix}") or None,
                twilio_from=st.text_input("Twilio sender number", value=config.TWILIO_FROM_NUMBER,
                                          key=f"msg_t_from_{suffix}") or None,
                telegram_token=st.text_input("Telegram bot token", value=config.TELEGRAM_BOT_TOKEN,
                                             type="password", key=f"msg_tg_tok_{suffix}") or None,
                telegram_chat_id=st.text_input("Telegram chat ID", value=config.TELEGRAM_CHAT_ID,
                                               key=f"msg_tg_cid_{suffix}") or None,
                webhook_url=st.text_input("Webhook URL", value=config.ALERT_WEBHOOK_URL,
                                          key=f"msg_wb_url_{suffix}") or None,
            )

        e1, e2 = st.columns(2)
        with e1:
            st.session_state["escalate_after_min"] = st.number_input(
                "Escalate to a call after (minutes)", min_value=1, max_value=240,
                value=int(st.session_state.get("escalate_after_min", config.ALERT_ESCALATE_AFTER_MIN)),
                key=f"escalate_after_{suffix}",
                help="A dispatched critical alert nobody acknowledges within this window becomes eligible "
                     "for a voice call on the Alerts page.",
            )
        with e2:
            st.session_state["auto_escalate_call"] = st.toggle(
                "Place escalation calls without asking",
                value=bool(st.session_state.get("auto_escalate_call", config.ALERT_AUTO_ESCALATE_CALL)),
                key=f"auto_escalate_{suffix}",
                help="Off by default. A call is an outward action, so it normally waits for a click on the "
                     "Alerts page. Each alert is called at most once either way.",
            )

        send_phone = phone or config.ALERT_RECIPIENT_PHONE
        if st.button(f"Send a test message to {send_phone}", key=f"msg_settings_send_test_{suffix}",
                     width="stretch", icon=":material/sms:"):
            from src.alerts import messages as alert_messages
            res = alert_messages.send_critical_alert(TEST_ALERT_EVENT, phone=send_phone, force=True, **creds)
            if res["status"] in ("delivered", "simulated"):
                st.success(f"Dispatched to {send_phone} ({res['detail']}).", icon=":material/check_circle:")
            else:
                st.error(f"Dispatch failed: {res.get('detail') or res.get('reason') or 'Unknown error'}",
                         icon=":material/cancel:")


def _render_firms_key_status(validate_key: str) -> None:
    """The key is read from .env and is never entered in the browser: FIRMS
    puts it in the request URL, so a pasted key would end up in logs and in
    error text. Settings only reports whether it loaded."""
    if config.FIRMS_API_KEY:
        st.success("FIRMS_API_KEY loaded from .env", icon=":material/check_circle:")
        if st.button("Validate key", key=validate_key, icon=":material/verified:"):
            try:
                check_map_key(config.FIRMS_API_KEY)
                st.success("Key is valid.", icon=":material/check_circle:")
            except FirmsAuthError as exc:
                st.error(str(exc), icon=":material/cancel:")
    else:
        st.warning("No FIRMS_API_KEY in .env. Live pulls will fail and the app will fall back to the "
                   "history stored by earlier live runs.", icon=":material/warning:")


def _render_settings_belt():
    with st.container(border=True):
        _section_header("Pipeline")
        _render_firms_key_status("settings_belt_validate")
        if st.button("Run pipeline", key="settings_belt_run", width="stretch", icon=":material/play_circle:"):
            run_and_cache()
            st.rerun()

    with st.container(border=True):
        _section_header("View")
        st.session_state["analyst_mode"] = st.toggle("Analyst mode", value=st.session_state["analyst_mode"], key="analyst_mode_toggle",
                                                       help="Expose raw features, model probabilities, and processing internals.")

    with st.container(border=True):
        _section_header("Operational parameters (prototype, not scientific constants)")
        min_days = st.slider("Persistence threshold (days)", 2, 15, config.PERSISTENCE_MIN_DAYS, key="settings_persist_slider")
        st.caption(f"Currently: ≥{min_days} distinct days in {config.PERSISTENCE_DEFAULT_WINDOW_DAYS} ⇒ persistent. "
                   "Changing it needs a pipeline re-run with the new threshold, which is not wired up yet.")

        st.markdown("**Risk Score Weights**")
        st.caption("Adjust and recompute to re-score the loaded data with these weights. "
                   "no re-fetch/re-classification needed, only the risk score, status, and alerts are recalculated.")
        w1, w2, w3 = st.columns(3)
        w_persistence = w1.slider("Persistence", 0.0, 1.0, config.RISK_WEIGHTS["persistence"], 0.05, key="w_persistence")
        w_frp = w2.slider("FRP", 0.0, 1.0, config.RISK_WEIGHTS["frp"], 0.05, key="w_frp")
        w_confidence = w3.slider("Confidence", 0.0, 1.0, config.RISK_WEIGHTS["confidence"], 0.05, key="w_confidence")
        w4, w5, _ = st.columns(3)
        w_industrial = w4.slider("Industrial proximity", 0.0, 1.0, config.RISK_WEIGHTS["industrial_proximity"], 0.05, key="w_industrial")
        w_recurrence = w5.slider("Recurrence", 0.0, 1.0, config.RISK_WEIGHTS["recurrence"], 0.05, key="w_recurrence")
        weight_total = w_persistence + w_frp + w_confidence + w_industrial + w_recurrence
        st.caption(f"Weights sum to {weight_total:.2f}. They need not be exactly 1.00: each component score is already "
                   "0-100, and the total is clamped to 0-100 either way).")
        if st.button("Recompute Risk Scores", key="recompute_risk_btn", width="stretch", icon=":material/calculate:"):
            custom_weights = {"persistence": w_persistence, "frp": w_frp, "confidence": w_confidence,
                               "industrial_proximity": w_industrial, "recurrence": w_recurrence}
            recompute_risk_and_cache(custom_weights)
            st.rerun()

    _render_alert_gateway_settings("belt")



def _route_regional_page(page: str):
    gdf = _load_cached_detail()
    cluster_df = _load_cached_clusters()
    alerts = _load_cached_alerts()
    run_info = st.session_state.get("run_info")

    if page == "Settings":
        _render_settings_belt()
        return

    if gdf is None or gdf.empty:
        st.info("No classified data yet for the Jharkhand and Odisha belt. Open Settings and run the pipeline "
                "to pull live NASA FIRMS detections for the region.", icon=":material/info:")
        return

    filtered, filtered_clusters, label_field, color_by = _apply_regional_filters(gdf, cluster_df, page)

    if page == "Overview":
        _render_kpis(gdf, cluster_df, alerts)
        _render_alert_banner(alerts)
        _render_overview(filtered, filtered_clusters, label_field, color_by)
    elif page == "Live Map":
        _render_live_map(filtered, label_field, color_by)
    elif page == "3D Globe":
        _render_3d_globe_page(filtered, filtered_clusters, is_regional=True)
    elif page == "Events":
        _render_events_table(filtered_clusters, "belt")
    elif page == "Alerts":
        _render_alerts_tab(alerts)
    elif page == "Cameras":
        _render_cameras_page(filtered_clusters)
    elif page == "Analytics":
        _render_analytics(filtered, filtered_clusters, run_info)
    elif page == "Investigations":
        _render_investigations(filtered_clusters, filtered, st.session_state["analyst_mode"])



def _render_kpis(gdf, cluster_df, alerts):
    # Observation -> Event -> Persistent Source funnel discipline (see
    # Methodology): event-level counts come from cluster_df (one row per
    # ~1km grid cell) so a single recurring source isn't recounted once per
    # daily detection the way a raw gdf-row sum would.
    n_total = len(gdf)
    n_events = int(cluster_df["grid_cell"].nunique()) if not cluster_df.empty else 0
    n_persistent = int(cluster_df["is_persistent"].sum()) if not cluster_df.empty and "is_persistent" in cluster_df else 0
    n_critical = sum(1 for a in alerts if a.get("severity") == "CRITICAL")

    _stat_row([
        ("Satellite observations", f"{n_total:,}"),
        ("Thermal events", f"{n_events:,}"),
        ("Persistent sources", f"{n_persistent:,}"),
        ("Critical alerts", f"{n_critical:,}"),
    ])


def _render_alert_banner(alerts):
    if not alerts:
        return
    n_critical = sum(1 for a in alerts if a.get("severity") == "CRITICAL")
    n_high = sum(1 for a in alerts if a.get("severity") == "HIGH")
    if n_critical == 0 and n_high == 0:
        return
    st.markdown(
        f'<div class="alertbar"><span class="txt"><b>{n_critical}</b> critical and <b>{n_high}</b> '
        f'high-priority thermal events are waiting for review.</span></div>',
        unsafe_allow_html=True,
    )


def _render_overview(filtered, filtered_clusters, label_field, color_by):
    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            _section_header("Daily detections")
            if not filtered.empty:
                daily = filtered.groupby([filtered["acq_date"].dt.date, label_field]).size().unstack(fill_value=0)
                st.line_chart(daily, color=[CATEGORY_COLORS.get(c, MUTED) for c in daily.columns])
    with c2:
        with st.container(border=True):
            _section_header("Top persistent clusters")
            if not filtered_clusters.empty:
                window_col = f"persistence_{config.PERSISTENCE_DEFAULT_WINDOW_DAYS}d"
                top = filtered_clusters.sort_values(window_col, ascending=False).head(8)
                st.dataframe(
                    top[["grid_cell", window_col, "detection_count", "avg_frp", "risk_score", "risk_level"]]
                    .rename(columns={"grid_cell": "Grid cell", window_col: "Days active",
                                     "detection_count": "Detections", "avg_frp": "Mean FRP (MW)",
                                     "risk_score": "Risk score", "risk_level": "Risk"}),
                    hide_index=True, width="stretch",
                )
            else:
                st.caption("No persistent clusters in the current filter selection.")


def _render_live_map(filtered, label_field, color_by):
    with st.container(border=True):
        hdr, toggle = st.columns([4.0, 1.0])
        with hdr:
            _section_header(f"{config.REGION_NAME}: {len(filtered):,} hotspots")
        timelapse_on = toggle.toggle("Time lapse")
        if filtered.empty:
            st.info("No hotspots match the current filters.", icon=":material/search_off:")
        elif timelapse_on:
            if len(filtered) > TIMELAPSE_MAX_POINTS:
                st.caption(f"Showing the {TIMELAPSE_MAX_POINTS} most recent of {len(filtered)} points for smooth playback.")
            st_folium(build_timelapse_map(filtered, label_field), width=None, height=660, returned_objects=[], key="map_live_timelapse")
        else:
            st_folium(build_map(filtered, label_field, color_by), width=None, height=660, returned_objects=[], key="map_live")



def _urgency_color(urgency: str) -> str:
    return {"Now": RISK_COLORS["CRITICAL"], "Today": RISK_COLORS["HIGH"],
            "This week": RISK_COLORS["MODERATE"]}.get(urgency, MUTED)


def _render_risk_explainer(item: dict, key: str):
    """Why the score is what it is, whether the model agrees, and what to do.
    The breakdown is exact arithmetic: the three weighted components add up to
    the score, so no attribution guesswork is involved."""
    factors = item.get("risk_factors") or []
    actions = item.get("actions") or []
    model = item.get("model_check") or {}
    if not factors and not actions:
        st.caption("No risk breakdown for this event. Re-run the pipeline to compute one.")
        return

    if item.get("risk_summary"):
        st.markdown(f'<div class="risk-lead">{item["risk_summary"]}</div>', unsafe_allow_html=True)

    if factors:
        rows = "".join(
            f'<div class="factor">'
            f'<div class="factor-head"><span class="name">{f["label"]}</span>'
            f'<span class="val">{f["value"]}</span>'
            f'<span class="pts">{f["points"]:.0f} pts</span></div>'
            f'<div class="bar"><span style="width:{max(2.0, f["share"] * 100):.0f}%"></span></div>'
            f'<div class="why">{f["detail"]}</div></div>'
            for f in factors
        )
        st.markdown(f'<div class="factors">{rows}</div>', unsafe_allow_html=True)

    if model:
        agrees = model.get("agrees")
        holdout = model.get("holdoutAgreement")
        verdict = (
            f"The model agrees with the rule label ({model.get('confidence', 0):.0%} confidence)."
            if agrees else
            f"The model would call this “{model.get('label')}” instead ({model.get('confidence', 0):.0%} "
            "confidence), so the rule label leans on something the numbers do not capture. Worth a look."
        )
        held = f" It reproduces the rules on {holdout:.0%} of held-out events." if holdout else ""
        st.markdown(
            f'<div class="model-note"><b>Model check.</b> {verdict}{held}<br>'
            f'<span class="caveat-inline">{model.get("caveat", "")}</span></div>',
            unsafe_allow_html=True,
        )

    if actions:
        steps = "".join(
            f'<li><span class="urgency" style="--u:{_urgency_color(a["urgency"])}">{a["urgency"]}</span>'
            f'<span class="step">{a["step"]}</span><span class="detail">{a["detail"]}</span></li>'
            for a in actions
        )
        st.markdown(f'<div class="actions"><p class="actions-title">What to do</p><ol>{steps}</ol></div>',
                    unsafe_allow_html=True)

    reasons = item.get("reasons") or []
    if reasons:
        with st.expander("Why this point is here", expanded=False):
            for r in reasons:
                st.markdown(f'<div class="evidence">{r}</div>', unsafe_allow_html=True)


def _render_escalation_queue(phone: str, key: str):
    """Dispatched alerts nobody has acknowledged yet. A text nobody reads is the
    same as no alert, so anything past the window can be escalated to a call."""
    from src.alerts import escalation

    window = int(st.session_state.get("escalate_after_min", config.ALERT_ESCALATE_AFTER_MIN))
    pending = escalation.pending()
    overdue = escalation.due(window)

    # Opt-in only, and each alert can escalate once, so a page that reruns on
    # every widget change cannot dial the same number over and over.
    if overdue and st.session_state.get("auto_escalate_call", config.ALERT_AUTO_ESCALATE_CALL):
        placed = escalation.escalate_due(window, phone=phone)
        if placed:
            st.warning(f"{len(placed)} alert(s) went unacknowledged past {window} minutes and were "
                       "escalated to a call automatically.", icon=":material/call:")
        pending, overdue = escalation.pending(), escalation.due(window)

    with st.container(border=True):
        _section_header(f"Awaiting acknowledgement ({len(pending)})")
        if not pending:
            st.caption("Nothing is waiting. Alerts appear here once dispatched, and clear when someone "
                       "acknowledges them.")
        else:
            st.caption(f"An alert with no acknowledgement after {window} minutes can be escalated to a "
                       "voice call, which is much harder to miss than a text.")
        for i, entry in enumerate(pending[:20]):
            waited = escalation.minutes_waiting(entry)
            late = waited >= window
            c1, c2, c3 = st.columns([3.4, 1.0, 1.0])
            with c1:
                st.markdown(
                    f'<div class="queue-row"><span class="mark" style="background:'
                    f'{RISK_COLORS["CRITICAL"] if late else RISK_COLORS["MODERATE"]}"></span>'
                    f'<span class="t">{entry.get("title")}</span>'
                    f'<span class="mono id">{entry.get("event_id")}</span>'
                    f'<span class="w">{"Overdue by" if late else "Waiting"} '
                    f'<b>{abs(waited - window) if late else waited:.0f} min</b></span></div>',
                    unsafe_allow_html=True,
                )
            if c2.button("Acknowledge", key=f"ack_{key}_{i}", width="stretch"):
                escalation.acknowledge(str(entry.get("event_id")))
                st.rerun()
            if c3.button("Call now", key=f"call_{key}_{i}", width="stretch", icon=":material/call:",
                         type="primary" if late else "secondary",
                         help=f"Ring {entry.get('phone') or phone} and read the escalation script"):
                res = escalation.place_call(entry, phone=entry.get("phone") or phone)
                if res["status"] == "failed":
                    st.error(f"Call failed: {res['detail']}", icon=":material/cancel:")
                else:
                    st.success(f"{res['detail']}", icon=":material/call:")
                    with st.expander("What the recipient hears"):
                        st.write(res["script"])

        if overdue:
            if st.button(f"Call all {len(overdue)} overdue", key=f"call_all_{key}",
                         icon=":material/call:", width="stretch"):
                results = escalation.escalate_due(window, phone=phone)
                st.success(f"Placed {len(results)} escalation call(s).", icon=":material/call:")
                st.rerun()

        # A call that leaves no trace is hard to audit, and the toast is gone on
        # the next rerun, so escalations stay visible here.
        called = [e for e in escalation.load() if e.get("state") == escalation.ESCALATED][:5]
        if called:
            with st.expander(f"Escalated to a call ({len(called)})"):
                for entry in called:
                    st.markdown(
                        f'<div class="queue-row"><span class="mark" style="background:{MUTED}"></span>'
                        f'<span class="t">{entry.get("title")}</span>'
                        f'<span class="mono id">{entry.get("event_id")}</span>'
                        f'<span class="w">{str(entry.get("escalated_at") or "")[:16].replace("T", " ")}</span>'
                        f'</div><div class="caveat" style="margin:0 0 .4rem;border:none;padding:0;">'
                        f'{entry.get("call_detail") or ""}</div>',
                        unsafe_allow_html=True,
                    )


def _render_alerts_tab(alerts):
    from src.alerts import escalation
    from src.alerts import messages as alert_messages

    phone = st.session_state.get("alert_phone", config.ALERT_RECIPIENT_PHONE)
    auto_active = st.session_state.get("alert_auto_dispatch", config.ALERT_AUTO_DISPATCH_CRITICAL)
    window = int(st.session_state.get("escalate_after_min", config.ALERT_ESCALATE_AFTER_MIN))

    with st.container(border=True):
        _section_header("Dispatch")
        d1, d2 = st.columns([3.0, 1.4])
        with d1:
            st.markdown(
                f'<div class="panel" style="padding:.6rem .9rem;">'
                f'<div class="row"><span class="k">Recipient</span><span class="v">{phone}</span></div>'
                f'<div class="row"><span class="k">Trigger</span><span class="v">Risk {config.ALERT_CRITICAL_RISK_MIN} or above</span></div>'
                f'<div class="row"><span class="k">Automatic dispatch</span><span class="v">'
                f'{"On" if auto_active else "Off"}</span></div>'
                f'<div class="row"><span class="k">Escalate to a call after</span>'
                f'<span class="v">{window} min unacknowledged</span></div></div>',
                unsafe_allow_html=True,
            )
        with d2:
            sample_event = alerts[0] if alerts else None
            if st.button("Send a test message", key="msg_send_test_top", width="stretch", icon=":material/sms:",
                         help=f"Send one test dispatch to {phone}", disabled=sample_event is None):
                res = alert_messages.send_critical_alert(sample_event, phone=phone, force=True)
                if res["status"] in ("delivered", "simulated"):
                    escalation.record_dispatch(sample_event, phone, channel=res["channel"])
                    st.success(f"Dispatched to {phone} ({res['detail']})", icon=":material/check_circle:")
                else:
                    st.error(f"Failed: {res.get('detail') or res.get('reason') or 'Unknown error'}",
                             icon=":material/cancel:")
            if sample_event is None:
                st.caption("A test uses the top live alert, so it needs at least one.")

        with st.expander("Dispatch log"):
            logs = alert_messages.load_critical_dispatch_log()
            if not logs:
                st.caption("Nothing dispatched yet.")
            else:
                log_df = pd.DataFrame(logs)[["timestamp", "recipient", "event_id", "risk_score", "severity",
                                             "status", "channel", "detail"]]
                st.dataframe(log_df, hide_index=True, width="stretch")

    _render_escalation_queue(phone, key="alerts")

    if not alerts:
        st.info("No alerts in the current live data.", icon=":material/info:")
        return

    _section_header(f"{len(alerts):,} open alerts")
    for i, a in enumerate(alerts[:50]):
        severity = str(a.get("severity", "MODERATE"))
        color = RISK_COLORS.get(severity, MUTED)
        event_id = str(a.get("event_id", a.get("grid_cell", "?")))
        days = int(a.get("persistence_days", 0) or 0)
        rank = a.get("priority")
        facts = [
            ("Risk", f'{float(a.get("risk_score", 0)):.0f}/100'),
            ("Location", f'{a["latitude"]:.3f}, {a["longitude"]:.3f}'),
            ("Active", f'{days} day' + ("" if days == 1 else "s")),
            ("Peak FRP", f'{a["frp"]:.1f} MW'),
        ]
        if rank is not None and pd.notna(rank):
            facts.insert(0, ("Priority", f"#{int(rank)}"))
        facts_html = "".join(
            f'<span class="fact"><span class="k">{k}</span><span class="v">{v}</span></span>'
            for k, v in facts
        )
        st.markdown(
            f'<div class="alertcard"><div class="title"><i class="sev" style="background:{color}"></i>'
            f'{a["title"]}<span class="mono" style="color:var(--ink2);font-weight:400;font-size:.85em;">'
            f'{event_id}</span></div>'
            f'<div class="facts">{facts_html}</div>'
            f'<div class="meta">{severity.capitalize()} severity. {a["classification"]}.</div></div>',
            unsafe_allow_html=True,
        )
        if st.button("Dispatch this alert", key=f"alert_crit_send_{i}", icon=":material/sms:",
                     help=f"Send this alert to {phone} and start the acknowledgement clock"):
            res = alert_messages.send_critical_alert(a, phone=phone, force=True)
            if res["status"] in ("delivered", "simulated"):
                escalation.record_dispatch(a, phone, channel=res["channel"])
                st.toast(f"Dispatched {event_id} to {phone}.", icon=":material/sms:")
                st.rerun()
            else:
                st.error(f"Dispatch failed: {res.get('detail') or res.get('reason') or 'Error'}",
                         icon=":material/cancel:")
        with st.expander("Why it is risky and what to do"):
            _render_risk_explainer(a, key=f"alert_{i}")


def _render_analytics(filtered, filtered_clusters, run_info):
    c1, c2 = st.columns(2)
    with c1:
        with st.container(border=True):
            _section_header("Classification distribution")
            if not filtered.empty:
                counts = filtered["rule_label"].value_counts()
                fig = go.Figure(go.Bar(x=counts.values, y=counts.index, orientation="h",
                                        marker_color=[CATEGORY_COLORS.get(l, MUTED) for l in counts.index], marker_line_width=0))
                _style_fig(fig, height=320)
                fig.update_layout(yaxis=dict(autorange="reversed"))
                st.plotly_chart(fig, width="stretch", key="chart_class_dist_belt")
    with c2:
        with st.container(border=True):
            _section_header("Risk distribution")
            if not filtered.empty:
                counts = filtered["risk_level"].value_counts().reindex(["LOW", "MODERATE", "HIGH", "CRITICAL"]).fillna(0)
                fig = go.Figure(go.Bar(x=counts.index, y=counts.values,
                                        marker_color=[RISK_COLORS[l] for l in counts.index], marker_line_width=0))
                _style_fig(fig, height=320)
                st.plotly_chart(fig, width="stretch", key="chart_risk_dist_belt")

    c3, c4 = st.columns(2)
    with c3:
        with st.container(border=True):
            _section_header("Persistence distribution (days active)")
            if not filtered.empty:
                st.bar_chart(filtered["persistence_days"].value_counts().sort_index())
    with c4:
        with st.container(border=True):
            _section_header("FRP distribution (MW)")
            if not filtered.empty:
                fig = go.Figure(go.Histogram(x=filtered["frp"], marker_color=SERIES, marker_line_width=0, nbinsx=30))
                _style_fig(fig, height=280)
                st.plotly_chart(fig, width="stretch", key="chart_frp_dist")

    if run_info:
        ml = run_info.get("ml_metrics", {})
        if ml.get("trained"):
            with st.container(border=True):
                _section_header("Feature importance")
                imp = pd.Series(ml["feature_importances"]).sort_values()
                st.bar_chart(imp)
                st.markdown(f'<div class="caveat">{ml.get("caveat", "")}</div>', unsafe_allow_html=True)

    with st.container(border=True):
        _section_header("Nearby events grouped into candidate sites")
        st.caption("DBSCAN over event coordinates (haversine distance, 2 km radius, 2 or more events) groups "
                   "adjacent ~1km grid-cell events that plausibly belong to one larger real-world site. This is a "
                   "spatial grouping heuristic, not a claim that grouped events share one cause.")
        if filtered_clusters is None or filtered_clusters.empty:
            st.caption("No events in the current filter selection.")
        else:
            _, spatial_summary = find_spatial_clusters(filtered_clusters)
            if spatial_summary.empty:
                st.caption("No multi-event spatial clusters in the current filter selection: events are "
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
        _section_header("Emerging thermal sources")
        st.caption("Not yet persistent, but recently active with rising FRP relative to their own short history. "
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

    _section_header("Most persistent clusters first. Select a row to investigate.")
    display_cols = ["rank", "event_id", "grid_cell", window_col, "detection_count", "avg_frp", "max_frp",
                     "dominant_label", "risk_score", "risk_level", "status", "latitude", "longitude"]
    display_cols = [c for c in display_cols if c in table.columns]
    event = st.dataframe(
        table[display_cols].rename(columns={
            "rank": "#", "event_id": "Event", "grid_cell": "Grid cell", window_col: "Days active",
            "detection_count": "Detections", "avg_frp": "Mean FRP (MW)", "max_frp": "Peak FRP (MW)",
            "dominant_label": "Classification", "risk_score": "Risk score", "risk_level": "Risk",
            "status": "Status", "latitude": "Latitude", "longitude": "Longitude",
        }),
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




# ------------------------------------------------------------- cameras --

CAMERA_COLOR = "#5cb8dc"


def _camera_player(camera: dict, height: int = 260):
    """Play one stream in the browser. HLS needs hls.js, which needs a real
    script tag, so this goes through a component iframe rather than markdown
    (Streamlit strips scripts from unsafe_allow_html)."""
    import streamlit.components.v1 as components
    from src.cameras import registry as camera_registry

    url = camera["stream_url"]
    kind = camera.get("stream_type") or camera_registry.infer_stream_type(url)
    frame = (
        "width:100%;height:100%;border:0;background:#0a0e13;display:block;"
        "object-fit:cover;border-radius:6px;"
    )

    if kind == "youtube":
        embed = camera_registry.youtube_embed(url) or url
        body = f'<iframe src="{embed}" style="{frame}" allow="autoplay; encrypted-media" allowfullscreen></iframe>'
    elif kind in ("mjpeg", "image"):
        # An MJPEG endpoint streams into an <img>; a still needs re-requesting.
        refresh = (
            f'<script>setInterval(function(){{var i=document.getElementById("shot");'
            f'i.src="{url}"+({"1" if "?" in url else "0"}?"&":"?")+"t="+Date.now();}}, 5000);</script>'
            if kind == "image" else ""
        )
        body = f'<img id="shot" src="{url}" style="{frame}" alt="{camera["name"]}">{refresh}'
    elif kind == "hls":
        body = f"""
        <video id="v" style="{frame}" muted autoplay playsinline controls></video>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/hls.js/1.5.17/hls.min.js"></script>
        <script>
          var v = document.getElementById('v'), src = {url!r};
          if (v.canPlayType('application/vnd.apple.mpegurl')) {{ v.src = src; }}
          else if (window.Hls && Hls.isSupported()) {{
            var h = new Hls({{ liveDurationInfinity: true }});
            h.loadSource(src); h.attachMedia(v);
            h.on(Hls.Events.ERROR, function (e, d) {{
              if (d.fatal) document.getElementById('msg').textContent =
                'Stream did not load (' + d.type + '). Check the URL is reachable and served over https.';
            }});
          }} else {{
            document.getElementById('msg').textContent = 'This browser cannot play HLS.';
          }}
        </script>"""
    else:
        body = f'<iframe src="{url}" style="{frame}" allowfullscreen></iframe>'

    components.html(
        f'<div style="height:{height}px">{body}</div>'
        f'<p id="msg" style="font:12px/1.5 \'IBM Plex Sans\',system-ui,sans-serif;color:#d03b3b;margin:.4rem 0 0"></p>',
        height=height + 26,
    )


def build_camera_map(cameras: list[dict], uncovered: pd.DataFrame, candidates: list[dict]) -> folium.Map:
    """Cameras with their coverage circles, the sites nobody is watching, and
    the suggested positions, on one map."""
    center_lat = (config.INDIA_BBOX["min_lat"] + config.INDIA_BBOX["max_lat"]) / 2
    center_lon = (config.INDIA_BBOX["min_lon"] + config.INDIA_BBOX["max_lon"]) / 2
    m = folium.Map(location=[center_lat, center_lon], zoom_start=5, tiles=None, control_scale=True)
    _add_base_layers(m)

    if not uncovered.empty:
        group = folium.FeatureGroup(name="Sites with no camera").add_to(m)
        for _, row in uncovered.iterrows():
            colour = RISK_COLORS.get(str(row.get("risk_level")), MUTED)
            folium.CircleMarker(
                location=[row["latitude"], row["longitude"]], radius=3,
                color=colour, fill=True, fill_color=colour, fill_opacity=0.8, weight=0.5,
                tooltip=f"{row.get('event_id', '')}: risk {float(row.get('risk_score', 0)):.0f}, no camera",
            ).add_to(group)

    if candidates:
        group = folium.FeatureGroup(name="Suggested camera positions").add_to(m)
        for i, c in enumerate(candidates, start=1):
            folium.CircleMarker(
                location=[c["latitude"], c["longitude"]], radius=7,
                color=ACCENT, fill=False, weight=2, dash_array="3",
                tooltip=f"Suggestion {i}: one camera here covers {c['events_covered']} flagged sites",
            ).add_to(group)

    if cameras:
        group = folium.FeatureGroup(name="Registered cameras").add_to(m)
        for camera in cameras:
            folium.Circle(
                location=[camera["latitude"], camera["longitude"]],
                radius=float(camera.get("coverage_km", 3.0)) * 1000,
                color=CAMERA_COLOR, weight=1, fill=True, fill_color=CAMERA_COLOR, fill_opacity=0.10,
                tooltip=f"{camera['name']}: {camera.get('coverage_km', 3.0)} km coverage",
            ).add_to(group)
            folium.CircleMarker(
                location=[camera["latitude"], camera["longitude"]], radius=5,
                color=CAMERA_COLOR, fill=True, fill_color=CAMERA_COLOR, fill_opacity=1, weight=1,
                popup=folium.Popup(
                    f'<div style="font-family:{FONT_STACK};font-size:12.5px;color:{INK};min-width:170px;">'
                    f'<b>{camera["name"]}</b><br><span style="color:{INK2};">'
                    f'{camera.get("operator") or "operator not recorded"}</span></div>', max_width=220),
            ).add_to(group)

    _add_map_chrome(m, _legend_html("Risk level of uncovered sites", RISK_COLORS))
    return m


def _render_camera_registry_form():
    from src.cameras import registry as camera_registry

    with st.container(border=True):
        _section_header("Register a camera")
        st.caption("The stream has to be one you are entitled to publish: a plant control room, a district "
                   "authority feed, or a public camera. Anything outside India is rejected, the same way the "
                   "hotspot pipeline drops detections outside Indian territory.")
        c1, c2 = st.columns(2)
        name = c1.text_input("Name", key="cam_name", placeholder="Rourkela Steel Plant, south gate")
        operator = c2.text_input("Operator", key="cam_operator", placeholder="SAIL Rourkela")
        c3, c4, c5 = st.columns(3)
        lat = c3.number_input("Latitude", value=22.2604, format="%.5f", key="cam_lat")
        lon = c4.number_input("Longitude", value=84.8536, format="%.5f", key="cam_lon")
        coverage = c5.number_input("Coverage radius (km)", min_value=0.1,
                                   max_value=float(camera_registry.MAX_COVERAGE_KM),
                                   value=float(camera_registry.DEFAULT_COVERAGE_KM), step=0.5, key="cam_radius",
                                   help="How far from the camera a detection is still identifiable on screen. "
                                        "Keep it modest so coverage is not overclaimed.")
        url = st.text_input("Stream URL", key="cam_url",
                            placeholder="https://example.org/live/stream.m3u8, a YouTube live link, or an MJPEG endpoint")
        c6, c7 = st.columns([1, 2])
        kind = c6.selectbox("Kind", camera_registry.KINDS, key="cam_kind")
        notes = c7.text_input("Notes", key="cam_notes", placeholder="What it points at, and who to call")

        if url:
            st.caption(f"Detected stream type: {camera_registry.infer_stream_type(url)}")

        if st.button("Add camera", key="cam_add", icon=":material/videocam:"):
            record, problems = camera_registry.add({
                "name": name, "operator": operator, "kind": kind, "latitude": lat, "longitude": lon,
                "stream_url": url, "coverage_km": coverage, "notes": notes,
            })
            if problems:
                for problem in problems:
                    st.error(problem, icon=":material/cancel:")
            else:
                st.success(f"Registered {record['name']} as {record['id']}.", icon=":material/check_circle:")
                st.rerun()


def _render_cameras_page(events_df: pd.DataFrame):
    from src.cameras import coverage as camera_coverage
    from src.cameras import registry as camera_registry

    cameras = camera_registry.load()
    active = [c for c in cameras if c.get("active", True)]
    report = camera_coverage.summary(events_df, active)

    _stat_row([
        ("Cameras registered", f"{len(cameras):,}"),
        ("High and critical sites", f"{report['n_flagged']:,}"),
        ("Covered by a camera", f"{report['n_covered']:,}"),
        ("Nobody watching", f"{report['n_uncovered']:,}"),
    ])
    if report["n_flagged"]:
        critical = report["n_critical_uncovered"]
        share = (
            "No camera covers any of them yet" if report["n_covered"] == 0
            else f"{report['coverage_share']:.0%} of them have a camera within its stated radius"
        )
        st.caption(
            f"{report['n_flagged']:,} sites in this run would be dispatched on. {share}. "
            f"{critical} critical site{'' if critical == 1 else 's'} nobody is watching."
        )

    # ── live view ──
    with st.container(border=True):
        _section_header("Live view")
        if not active:
            st.info(
                "No cameras registered yet. There is no public live CCTV feed covering Indian industrial "
                "sites, so nothing can be filled in automatically: plant cameras are private systems, and the "
                "open aggregators list a handful of tourism and weather cameras nationwide. Add a stream you "
                "hold the access to below, and the coverage analysis underneath already works without one.",
                icon=":material/videocam_off:",
            )
        else:
            watching = [c for c in active if len(report["by_camera"].get(c["id"], [])) > 0]
            idle = [c for c in active if c not in watching]
            if watching:
                st.caption(f"{len(watching)} camera{'' if len(watching) == 1 else 's'} with a flagged site "
                           "inside coverage right now.")
            for camera in watching + idle:
                seen = report["by_camera"].get(camera["id"], pd.DataFrame())
                v1, v2 = st.columns([2.0, 1.6])
                with v1:
                    _camera_player(camera, height=260)
                with v2:
                    st.markdown(
                        f'<div class="panel" style="padding:.7rem .95rem;">'
                        f'<div class="row"><span class="k">Camera</span><span class="v">{camera["name"]}</span></div>'
                        f'<div class="row"><span class="k">Operator</span><span class="v">'
                        f'{camera.get("operator") or "not recorded"}</span></div>'
                        f'<div class="row"><span class="k">Position</span><span class="v">'
                        f'{camera["latitude"]:.4f}, {camera["longitude"]:.4f}</span></div>'
                        f'<div class="row"><span class="k">Coverage</span><span class="v">'
                        f'{camera.get("coverage_km", 3.0)} km</span></div>'
                        f'<div class="row"><span class="k">Flagged sites in view</span><span class="v">'
                        f'{len(seen)}</span></div></div>',
                        unsafe_allow_html=True,
                    )
                    if len(seen):
                        st.dataframe(
                            seen[[c for c in ("event_id", "risk_score", "risk_level", "distance_km")
                                  if c in seen.columns]]
                            .rename(columns={"event_id": "Event", "risk_score": "Risk",
                                             "risk_level": "Tier", "distance_km": "km"}),
                            hide_index=True, width="stretch", height=150,
                        )
                    else:
                        st.caption("Nothing flagged inside this camera's radius in the current run.")

    # ── gaps ──
    with st.container(border=True):
        _section_header("Where a camera would help most")
        if report["n_uncovered"] == 0 and report["n_flagged"]:
            st.success("Every high and critical site in this run is inside a registered camera's radius.",
                       icon=":material/check_circle:")
        elif not report["candidates"]:
            st.caption("No high or critical sites in the current run, so there is nothing to cover.")
        else:
            st.caption(
                f"Greedy coverage over the {report['n_uncovered']:,} unwatched sites, assuming a "
                f"{report['radius_km']:.1f} km radius. Each row is a position where one camera would see the "
                "most sites nothing is currently watching, best first."
            )
            table = pd.DataFrame([{
                "Sites covered": c["events_covered"],
                "Highest risk": round(c["max_risk"]),
                "Place": c["place"] or "",
                "District": c["district"] or "",
                "State": c["state"] or "",
                "Nearest facility": (c["facility"] or {}).get("name") if isinstance(c["facility"], dict) else "",
                "Latitude": c["latitude"],
                "Longitude": c["longitude"],
            } for c in report["candidates"]])
            st.dataframe(table, hide_index=True, width="stretch")

    with st.container(border=True):
        _section_header("Coverage map")
        st_folium(
            build_camera_map(active, report["uncovered"], report["candidates"]),
            width=None, height=560, returned_objects=[], key="map_cameras",
        )

    _render_camera_registry_form()

    if cameras:
        with st.container(border=True):
            _section_header(f"Registered cameras ({len(cameras)})")
            for i, camera in enumerate(cameras):
                c1, c2, c3 = st.columns([4.0, 1.0, 1.0])
                c1.markdown(
                    f'<div class="queue-row"><span class="mark" style="background:'
                    f'{CAMERA_COLOR if camera.get("active", True) else MUTED}"></span>'
                    f'<span class="t">{camera["name"]}</span>'
                    f'<span class="mono id">{camera["id"]}</span>'
                    f'<span class="w">{camera.get("kind", "Other")}, {camera.get("stream_type")}, '
                    f'{camera.get("coverage_km", 3.0)} km</span></div>',
                    unsafe_allow_html=True,
                )
                label = "Disable" if camera.get("active", True) else "Enable"
                if c2.button(label, key=f"cam_toggle_{i}", width="stretch"):
                    camera_registry.set_active(camera["id"], not camera.get("active", True))
                    st.rerun()
                if c3.button("Remove", key=f"cam_remove_{i}", width="stretch"):
                    camera_registry.remove(camera["id"])
                    st.rerun()


# ---------------------------------------------------------- national mode --

NATIONAL_MODES = ["Raw hotspots", "Events", "Persistent sources", "Industrial sources", "High risk", "Critical"]


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
            return {"color": "#5cb8dc", "weight": 1, "fillColor": "#5cb8dc", "fillOpacity": 0.02}

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
                style=f"font-family:{FONT_STACK};font-size:12px;background:{SURFACE};color:{INK};border:1px solid {LINE};padding:4px 8px;border-radius:4px;",
            ),
        ).add_to(m)
    except Exception as exc:
        print(f"[app] state boundary layer failed: {exc}")

    # The detailed-pipeline region, outlined so it reads as a named area
    # rather than an alert.
    belt_popup_html = (
        f'<div style="font-family:{FONT_STACK};font-size:12.5px;line-height:1.6;padding:4px;min-width:210px;color:{INK};">'
        f'<b style="font-size:13px;">{config.REGION_NAME}</b><br>'
        f'<span style="color:{INK2};">Detailed pipeline region: OpenStreetMap industrial and mining context, '
        f'rule and model classification, and anomaly detection all run here.</span><br>'
        f'<span style="color:{INK2};font-size:11px;">Switch Region in the top bar to open it.</span>'
        f'</div>'
    )
    folium.Rectangle(
        bounds=[[config.BBOX["min_lat"], config.BBOX["min_lon"]], [config.BBOX["max_lat"], config.BBOX["max_lon"]]],
        color="#fab219", weight=1.5, fill=True, fill_color="#fab219", fill_opacity=0.06, dash_array="4, 4",
        tooltip=config.REGION_NAME,
        popup=folium.Popup(belt_popup_html, max_width=250),
        name=f"Detailed region: {config.REGION_NAME}",
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
            color = RISK_COLORS.get(risk_key, "#5cb8dc")
            risk_score_value = row.get("risk_score", 0)
            risk_pct = max(0.0, min(100.0, float(risk_score_value or 0)))
            frp_value = row.get("frp", row.get("avg_frp", 0))
            frp = float(frp_value) if frp_value is not None else 0.0
            popup = (
                f'<div style="font-family:{FONT_STACK};font-size:12.5px;line-height:1.6;min-width:180px;">'
                f"<b style='color:{color}'>{row.get('event_id', row.get('grid_cell', '?'))}</b><br>"
                f"<span style='color:#a1adba;'>{row.get('state', 'Unknown state')}</span><br>"
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

    _add_map_chrome(m, _legend_html("Risk level", RISK_COLORS))
    return m


def _apply_national_filters(detail_df: pd.DataFrame, page: str):
    show_ui = page == "Live Map"
    states_available = sorted(s for s in detail_df["state"].dropna().unique())
    satellites_available = sorted(detail_df["satellite"].dropna().unique().astype(str))
    frp_max_n = float(detail_df["frp"].max()) if not detail_df.empty else 20.0

    if show_ui:
        with st.container(border=True):
            _section_header("Filters")
            f1, f2, f3, f4 = st.columns(4)
            state_filter = f1.multiselect("State", states_available, default=states_available, key=f"nstate_{page}")
            satellite_filter = f2.multiselect("Satellite", satellites_available, default=satellites_available, key=f"nsat_{page}")
            risk_filter = f3.multiselect("Risk", list(RISK_COLORS.keys()), default=list(RISK_COLORS.keys()), key=f"nrisk_{page}")
            map_mode = f4.selectbox("Map mode", NATIONAL_MODES, key=f"nmode_{page}")

            g1, g2, g3, g4 = st.columns(4)
            min_conf_n = g1.slider("Minimum confidence", 0, 100, 0, key=f"nconf_{page}")
            min_persist_n = g2.slider("Minimum persistence (days)", 0, config.NATIONAL_DAY_RANGE, 0, key=f"npers_{page}")
            frp_range_n = g3.slider("FRP range (MW)", 0.0, max(frp_max_n, 1.0), (0.0, max(frp_max_n, 1.0)), key=f"nfrp_{page}")
            show_heatmap = g4.checkbox("Heatmap layer", key=f"nheat_{page}")
    else:
        state_filter, satellite_filter, risk_filter = states_available, satellites_available, list(RISK_COLORS.keys())
        min_conf_n, min_persist_n = 0, 0
        frp_range_n = (0.0, max(frp_max_n, 1.0))
        map_mode, show_heatmap = "Persistent sources", False

    mask = (
        detail_df["state"].isin(state_filter) & detail_df["satellite"].astype(str).isin(satellite_filter)
        & detail_df["risk_level"].isin(risk_filter) & (detail_df["confidence_numeric"] >= min_conf_n)
        & (detail_df["persistence_days"] >= min_persist_n) & detail_df["frp"].between(*frp_range_n)
    )
    filtered_detail = detail_df[mask]
    return filtered_detail, state_filter, map_mode, show_heatmap


def _map_points_for_mode(filtered_detail: pd.DataFrame, filtered_events: pd.DataFrame, map_mode: str) -> pd.DataFrame:
    if map_mode == "Raw hotspots":
        return filtered_detail
    if map_mode == "Persistent sources":
        return filtered_events[filtered_events["is_persistent"]] if not filtered_events.empty else filtered_events
    if map_mode == "High risk":
        return filtered_events[filtered_events["risk_level"] == "HIGH"] if not filtered_events.empty else filtered_events
    if map_mode == "Critical":
        return filtered_events[filtered_events["risk_level"] == "CRITICAL"] if not filtered_events.empty else filtered_events
    if map_mode == "Industrial sources":
        return filtered_events.iloc[0:0]
    return filtered_events  # Events


# ----------------------------------------------------------------- globe --


def _render_3d_globe_page(filtered_data: pd.DataFrame | gpd.GeoDataFrame | None,
                          filtered_clusters_or_events: pd.DataFrame | None,
                          is_regional: bool = True):
    from src.utils.export_3d_globe import (
        export_pipeline_events_for_holo_view,
        load_or_export_holo_events,
    )

    # Counted the way the globe shows them by default (corroborated only), so
    # the numbers here and inside the globe agree.
    events = load_or_export_holo_events()
    shown = [e for e in events if e.get("corroborated", True)]
    n_critical = sum(1 for e in shown if e.get("riskLevel") == "CRITICAL")
    n_high = sum(1 for e in shown if e.get("riskLevel") == "HIGH")
    total_frp = sum(float(e.get("frp", 0)) for e in shown)

    h1, h2 = st.columns([4.0, 1.2])
    with h1:
        _section_header("3D globe")
        st.caption("Live NASA FIRMS hotspots inside India, each one explained with open-source context: "
                   "the nearest mapped facility, the nearest town, and the satellite passes that saw it.")
    with h2:
        if st.button("Re-export", key="sync_3d_globe_top", width="stretch", icon=":material/sync:",
                     help="Write the current run to the globe's events.json again"):
            with st.spinner("Exporting thermal events..."):
                if is_regional:
                    exported = export_pipeline_events_for_holo_view(_load_cached_detail(), _load_cached_clusters())
                else:
                    info = st.session_state.get("national_info")
                    exported = export_pipeline_events_for_holo_view(
                        events_df=info.get("events_df") if info else None,
                        national_detail_df=info.get("detail_df") if info else None,
                    )
                st.session_state["holo_events_count"] = len(exported)
                st.session_state["holo_last_synced"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
                st.rerun()

    _stat_row([
        (f"Corroborated of {len(events):,}", f"{len(shown):,}"),
        ("Critical risk", f"{n_critical:,}"),
        ("High risk", f"{n_high:,}"),
        ("Total radiative power", f"{total_frp:,.0f} MW"),
    ])

    # The globe itself: the holo-view-maker MapLibre app, embedded so the
    # dashboard and the globe are one site on one live run.
    holo_url = (st.session_state.get("holo_host_url") or HOLO_DEFAULT_URL).rstrip("/")
    if _holo_app_reachable(holo_url):
        st.iframe(f"{holo_url}/?embed=1", height=900)
        g1, g2 = st.columns([4, 1])
        with g1:
            st.caption("Drag to rotate, scroll to zoom, click a hotspot to see why it is there. "
                       "Press ? inside the globe for shortcuts.")
        with g2:
            st.link_button("Open full screen", holo_url, width="stretch", icon=":material/open_in_new:")
    else:
        st.warning(
            f"The globe server is not answering at {holo_url}. Start the dashboard and the globe together with "
            "python start_all.py, or run npm run dev inside holo-view-maker, then reload this page.",
            icon=":material/warning:",
        )

    with st.expander("Export and server details"):
        st.caption("Written to holo-view-maker/public/data/events.json and output/holo_events.json, in the "
                   "ThermalEvent shape declared in holo-view-maker/src/lib/thermal.ts.")
        st.session_state["holo_host_url"] = st.text_input(
            "Globe server address", value=holo_url, key="holo_url_input_box",
            help=f"Where holo-view-maker is served. Default: {HOLO_DEFAULT_URL}",
        )
        st.download_button("Download events.json", json.dumps(events, indent=2), "events.json",
                           "application/json", key="download_holo_json_btn")




def _render_national_kpis(filtered_detail: pd.DataFrame, filtered_events: pd.DataFrame):
    n_persistent = int(filtered_events["is_persistent"].sum()) if not filtered_events.empty else 0
    n_critical = int((filtered_events["risk_level"] == "CRITICAL").sum()) if not filtered_events.empty else 0
    # hotspots the open-source context credits to a known facility (OSM / WRI)
    at_sites = (
        int(filtered_events["facility"].map(lambda f: isinstance(f, dict)).sum())
        if "facility" in filtered_events.columns and not filtered_events.empty else 0
    )
    _stat_row([
        ("Satellite hotspots", f"{len(filtered_detail):,}"),
        ("Detected events", f"{len(filtered_events):,}"),
        ("Persistent sources", f"{n_persistent:,}"),
        ("At known industrial sites", f"{at_sites:,}"),
    ])
    # FIRMS VIIRS codes to names ("N" alone reads like a typo, but it is Suomi NPP);
    # MODIS already reports "Aqua"/"Terra" directly, so those pass through as-is.
    sat_names = {"N": "S-NPP", "N20": "NOAA-20", "N21": "NOAA-21", "Aqua": "Aqua (MODIS)", "Terra": "Terra (MODIS)"}
    satellites = sorted(
        sat_names.get(s, s) for s in filtered_detail["satellite"].dropna().astype(str).unique()
    ) if not filtered_detail.empty else []
    n_states = int(filtered_detail["state"].nunique()) if not filtered_detail.empty else 0
    st.caption(f"{n_critical} critical events · {n_states} states with activity · "
               f"Satellites: {', '.join(satellites) or 'none'}")


def _render_national_map_panel(filtered_detail: pd.DataFrame, filtered_events: pd.DataFrame,
                                map_mode: str, show_heatmap: bool, key: str):
    map_points = _map_points_for_mode(filtered_detail, filtered_events, map_mode)
    with st.container(border=True):
        _section_header(f"India: {map_mode.lower()}, {len(map_points):,} shown")

        if map_mode == "Industrial sources":
            st.info("Industrial-zone classification needs the OpenStreetMap join, which only runs for the detailed "
                    "Jharkhand and Odisha belt. Running it for all of India on every load would be far too slow. "
                    "Switch Region in the top bar for the detailed view.", icon=":material/info:")
        elif map_points.empty:
            st.info("No observations match the current filters.", icon=":material/search_off:")
        else:
            # Region no longer auto-switches on a map click: it was jumping to
            # the belt (and away from the India view) just from clicking near
            # it on the map, with no way to opt out. The Region selector in the
            # top bar is the only way in now.
            st_folium(
                build_national_map(map_points, map_mode, show_heatmap),
                width=None,
                height=620,
                returned_objects=[],
                key=key,
            )


def _render_national_top_states_chart(state_summary: pd.DataFrame, state_filter: list[str]):
    with st.container(border=True):
        _section_header("Top states by thermal activity")
        if state_summary.empty:
            st.caption("No state summary available yet.")
            return
        top_states = state_summary[state_summary["state"].isin(state_filter)].head(10)
        fig = go.Figure(go.Bar(x=top_states["hotspots"], y=top_states["state"], orientation="h",
                                marker_color=SERIES, marker_line_width=0,
                                hovertemplate="%{y}: %{x:,} hotspots<extra></extra>"))
        _style_fig(fig, height=340)
        fig.update_layout(yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, width="stretch", key="chart_top_states")


def _render_national_analytics(filtered_detail: pd.DataFrame, filtered_events: pd.DataFrame,
                                state_summary: pd.DataFrame, state_filter: list[str]):
    c1, c2 = st.columns(2)
    with c1:
        _render_national_top_states_chart(state_summary, state_filter)
    with c2:
        with st.container(border=True):
            _section_header("Risk distribution across events")
            if filtered_events.empty:
                st.caption("No events in the current filter selection.")
            else:
                counts = filtered_events["risk_level"].value_counts().reindex(["LOW", "MODERATE", "HIGH", "CRITICAL"]).fillna(0)
                fig = go.Figure(go.Bar(x=counts.index, y=counts.values, marker_color=[RISK_COLORS[l] for l in counts.index], marker_line_width=0))
                _style_fig(fig, height=340)
                st.plotly_chart(fig, width="stretch", key="chart_risk_dist_national")

    with st.container(border=True):
        _section_header("Activity by state")
        if not state_summary.empty:
            st.dataframe(
                state_summary[state_summary["state"].isin(state_filter)]
                .rename(columns={"state": "State", "hotspots": "Hotspots",
                                  "persistent_sources": "Persistent", "high_risk": "High risk",
                                  "critical": "Critical"}),
                hide_index=True, width="stretch",
            )




def _render_settings_national():
    info = st.session_state.get("national_info") or {}
    with st.container(border=True):
        _section_header("Pipeline")
        _render_firms_key_status("settings_nat_validate")
        if st.button("Run pipeline", key="settings_nat_run", width="stretch", icon=":material/play_circle:"):
            run_national_and_cache()
            st.rerun()
        st.caption("Switch Region in the top bar to the Jharkhand and Odisha belt to run the detailed "
                   "pipeline instead.")

    with st.container(border=True):
        _section_header("Data window")
        st.caption(f"Each live run pulls the latest {config.NATIONAL_DAY_RANGE * 24} hours from NASA FIRMS and "
                   f"merges it into a persistent store. Persistence is then judged over up to a "
                   f"{config.NATIONAL_HISTORY_DAYS}-day rolling window of accumulated history "
                   f"({config.NATIONAL_PERSISTENCE_MIN_DAYS_HISTORY} or more active days counts as persistent), "
                   f"falling back to the fresh batch alone ({config.NATIONAL_PERSISTENCE_MIN_DAYS} or more active "
                   "days) before any history has accumulated.")
        weights = ", ".join(f"{k.replace('frp', 'FRP')} {v:.0%}" for k, v in config.NATIONAL_RISK_WEIGHTS.items())
        st.caption(f"History currently stored: {info.get('history_days_covered', 0)} days. Risk weights: {weights}")

    _render_alert_gateway_settings("india")


def _route_national_page(page: str):
    if page == "Settings":
        _render_settings_national()
        return

    info = st.session_state.get("national_info")
    if not info:
        st.info("No national data yet. Open Settings and run the pipeline to pull the latest live NASA FIRMS "
                "observations for India.", icon=":material/info:")
        return

    detail_df: pd.DataFrame = info["detail_df"]
    events_df: pd.DataFrame = info["events_df"]
    state_summary: pd.DataFrame = info["state_summary"]
    alerts = _derive_national_alerts(events_df)

    filtered_detail, state_filter, map_mode, show_heatmap = _apply_national_filters(detail_df, page)
    filtered_event_cells = set(filtered_detail["grid_cell"])
    filtered_events = events_df[events_df["grid_cell"].isin(filtered_event_cells)] if not events_df.empty else events_df

    if page == "Overview":
        _render_national_kpis(filtered_detail, filtered_events)
        _render_national_alert_banner(alerts)
        _render_national_top_states_chart(state_summary, state_filter)
    elif page == "Live Map":
        _render_national_map_panel(filtered_detail, filtered_events, map_mode, show_heatmap, key="map_national_livemap")
    elif page == "3D Globe":
        _render_3d_globe_page(filtered_detail, filtered_events, is_regional=False)
    elif page == "Events":
        _render_events_table(filtered_events, "india")
    elif page == "Alerts":
        _render_alerts_tab(alerts)
    elif page == "Cameras":
        _render_cameras_page(filtered_events)
    elif page == "Analytics":
        _render_national_analytics(filtered_detail, filtered_events, state_summary, state_filter)
    elif page == "Investigations":
        st.info("Investigations need the OpenStreetMap join and rule classification, which only run for the "
                "detailed Jharkhand and Odisha belt. Running them for all of India on every load would be far "
                "too slow.", icon=":material/info:")
        st.button("Open the belt view", key="nav_restricted_investigations", icon=":material/map:",
                  on_click=_navigate(page="Investigations", region="jharkhand_odisha"))


def _render_national_alert_banner(alerts: list[dict]):
    _render_alert_banner(alerts)


if __name__ == "__main__":
    main()
