"""Streamlit dashboard: AI-Based Detection & Classification of Industrial
Fires and Persistent Thermal Sources (SIH26162).

Run with: streamlit run app.py
"""
from __future__ import annotations

import folium
import geopandas as gpd
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

import config
from src import pipeline

st.set_page_config(page_title="Industrial Thermal Source Detector", layout="wide", page_icon="\U0001F525")

CATEGORY_COLORS = {
    "Industrial Fire": "#d62728",
    "Persistent Non-Industrial Thermal Source": "#ff7f0e",
    "Industrial Flare / Transient Activity": "#9467bd",
    "Likely Agricultural Burning": "#2ca02c",
    "Likely Noise / Sun Glint": "#7f7f7f",
    "Unclassified / Needs Review": "#1f1f1f",
}


@st.cache_data(show_spinner=False)
def _load_cached_output() -> gpd.GeoDataFrame | None:
    if config.CLASSIFIED_GEOJSON.exists():
        gdf = gpd.read_file(config.CLASSIFIED_GEOJSON)
        gdf["acq_date"] = pd.to_datetime(gdf["acq_date"])
        return gdf
    return None


def run_pipeline_and_cache(map_key: str | None):
    with st.spinner("Running pipeline: fetching hotspots, joining OSM zones, scoring, training ML layer..."):
        try:
            _gdf, info = pipeline.run_pipeline(map_key=map_key)
        except Exception as exc:
            st.error(f"Pipeline run failed: {exc}")
            return
    _load_cached_output.clear()
    st.session_state["run_info"] = info
    st.success(
        f"Done — {info['n_hotspots']} hotspots classified "
        f"(hotspots: {info['hotspot_source']}, zones: {info['zone_source']}, "
        f"{info['n_industrial_zones']} industrial zones)."
    )


def build_map(gdf: gpd.GeoDataFrame, label_field: str) -> folium.Map:
    center_lat = (config.BBOX["min_lat"] + config.BBOX["max_lat"]) / 2
    center_lon = (config.BBOX["min_lon"] + config.BBOX["max_lon"]) / 2
    m = folium.Map(location=[center_lat, center_lon], zoom_start=8, tiles="CartoDB positron")

    folium.Rectangle(
        bounds=[
            [config.BBOX["min_lat"], config.BBOX["min_lon"]],
            [config.BBOX["max_lat"], config.BBOX["max_lon"]],
        ],
        color="#3388ff",
        weight=1,
        fill=False,
        dash_array="4",
        tooltip="Target region bounding box",
    ).add_to(m)

    for _, row in gdf.iterrows():
        label = row[label_field]
        color = CATEGORY_COLORS.get(label, "#000000")
        popup_html = (
            f"<b>{label}</b><br>"
            f"<i>{row.get('rule_reason', '')}</i><br>"
            f"Date: {row['acq_date']} ({row.get('daynight', '?')})<br>"
            f"FRP: {row['frp']:.1f} MW · Confidence: {row['confidence_numeric']:.0f}<br>"
            f"Persistence: {row['persistence_days']} days · Zone: {row['zone_type']}<br>"
            f"Satellite: {row.get('satellite', '?')} / {row.get('instrument', '?')} · Cell: {row.get('grid_cell', '?')}"
        )
        folium.CircleMarker(
            location=[row.geometry.y, row.geometry.x],
            radius=4 + min(row["frp"], 40) / 10,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.75,
            weight=1,
            popup=folium.Popup(popup_html, max_width=280),
        ).add_to(m)

    legend_items = "".join(
        f'<i style="background:{c};width:10px;height:10px;display:inline-block;margin-right:6px;'
        f'border-radius:50%;"></i>{label}<br>'
        for label, c in CATEGORY_COLORS.items()
    )
    legend_html = f"""
    <div style="position: fixed; bottom: 30px; left: 30px; z-index: 9999;
        background: white; padding: 10px 14px; border-radius: 6px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.3); font-size: 12px; line-height: 1.6;">
        <b>Classification</b><br>{legend_items}
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))  # pyright: ignore[reportAttributeAccessIssue] — folium's Figure.html exists at runtime, stub types get_root() too generically
    return m


def main():
    st.title("\U0001F525 AI-Based Detection & Classification of Industrial Fires")
    st.caption(
        "SIH26162 · Ministry: NTRO · Jharkhand–Odisha Iron Ore & Steel Belt "
        "(Jamshedpur, Rourkela, Keonjhar, Sundargarh, West Singhbhum, Jharia)"
    )

    with st.sidebar:
        st.header("Pipeline")
        key_configured = bool(config.FIRMS_MAP_KEY)
        if key_configured:
            st.success("FIRMS_MAP_KEY loaded from .env")
        else:
            st.warning(
                "No FIRMS_MAP_KEY set — running on synthetic sample data. "
                "Get a free key at firms.modaps.eosdis.nasa.gov and add it to .env."
            )
        manual_key = st.text_input("Or paste a FIRMS key for this session", type="password")
        if st.button("\U0001F504 Run / Refresh Pipeline", width="stretch"):
            run_pipeline_and_cache(manual_key or None)
            st.rerun()

        st.divider()
        st.header("Filters")

    gdf = _load_cached_output()
    if gdf is None or gdf.empty:
        st.info("No classified data yet. Click **Run / Refresh Pipeline** in the sidebar to generate it.")
        return

    run_info = st.session_state.get("run_info")

    with st.sidebar:
        min_date, max_date = gdf["acq_date"].min().date(), gdf["acq_date"].max().date()
        if min_date == max_date:
            date_range = (min_date, max_date)
            st.caption(f"All data is from {min_date}")
        else:
            date_range = st.slider(
                "Date range", min_value=min_date, max_value=max_date, value=(min_date, max_date)
            )
        min_conf = st.slider("Min confidence", 0, 100, 0)
        label_field = st.radio("Classification source", ["rule_label", "ml_label"], horizontal=True)
        categories = st.multiselect(
            "Categories", options=list(CATEGORY_COLORS.keys()), default=list(CATEGORY_COLORS.keys())
        )
        persistent_only = st.checkbox("Persistent sources only")

    mask = (
        (gdf["acq_date"].dt.date >= date_range[0])
        & (gdf["acq_date"].dt.date <= date_range[1])
        & (gdf["confidence_numeric"] >= min_conf)
        & (gdf[label_field].isin(categories))
    )
    if persistent_only:
        mask &= gdf["is_persistent"].astype(bool)
    filtered = gdf[mask]

    n_persistent = int(gdf["is_persistent"].sum())
    n_industrial_fire = int((gdf["rule_label"] == "Industrial Fire").sum())
    n_review = int((gdf["rule_label"] == "Unclassified / Needs Review").sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total hotspots", len(gdf))
    c2.metric("Persistent sources", n_persistent)
    c3.metric("Industrial fires", n_industrial_fire)
    c4.metric("Needs review", n_review)

    if run_info:
        src_note = f"hotspots: **{run_info['hotspot_source']}** · industrial zones: **{run_info['zone_source']}**"
        if run_info["hotspot_source"] == "sample_data":
            st.warning(f"Showing synthetic demo data ({src_note}). Add a FIRMS key for live satellite data.")
        else:
            st.caption(src_note)
        ml_metrics = run_info.get("ml_metrics", {})
        if ml_metrics.get("trained"):
            with st.expander("ML layer diagnostics (Random Forest trained on rule labels)"):
                st.write(f"Accuracy on held-out split: **{ml_metrics['accuracy']:.2%}**")
                st.bar_chart(pd.Series(ml_metrics["feature_importances"]).sort_values())
                st.text(ml_metrics["classification_report"])

    st.subheader(f"Map ({len(filtered)} hotspots shown)")
    if filtered.empty:
        st.info("No hotspots match the current filters.")
    else:
        m = build_map(filtered, label_field)
        st_folium(m, width=None, height=600, returned_objects=[])

    if not filtered.empty:
        st.subheader("Trends & top persistent clusters")
        t1, t2 = st.columns(2)
        daily = filtered.groupby([filtered["acq_date"].dt.date, label_field]).size().unstack(fill_value=0)
        t1.caption("Daily detections by category")
        t1.line_chart(daily)
        t2.caption("Detections by persistence (days active)")
        t2.bar_chart(filtered["persistence_days"].value_counts().sort_index())

        top_clusters = (
            filtered[filtered["is_persistent"]]
            .groupby("grid_cell")
            .agg(
                days_active=("persistence_days", "max"),
                label=(label_field, lambda s: s.mode().iat[0]),
                avg_frp=("frp", "mean"),
                lat=("latitude", "mean"),
                lon=("longitude", "mean"),
            )
            .sort_values("days_active", ascending=False)
            .head(10)
            .round(3)
        )
        if not top_clusters.empty:
            st.dataframe(top_clusters, width="stretch")

    st.subheader("Export")
    e1, e2 = st.columns(2)
    e1.download_button(
        "\U0001F4E5 Download filtered CSV", filtered.drop(columns="geometry").to_csv(index=False),
        "classified_hotspots.csv", "text/csv", width="stretch",
    )
    e2.download_button(
        "\U0001F4E5 Download filtered GeoJSON", filtered.to_json(),
        "classified_hotspots.geojson", "application/geo+json", width="stretch",
    )

    with st.expander("Raw classified data"):
        st.dataframe(
            filtered.drop(columns="geometry")[
                ["acq_date", "latitude", "longitude", "frp", "confidence_numeric", "persistence_days",
                 "is_persistent", "zone_type", "rule_label", "rule_reason", "ml_label"]
            ].sort_values("acq_date", ascending=False),
            width="stretch",
        )


if __name__ == "__main__":
    main()
