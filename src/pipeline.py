"""Top-level orchestration: fetch -> clean -> geospatial join -> classify ->
alerts -> persist output.

Live data only:

    LIVE FIRMS API -> LOCAL CACHE of a previous live pull -> clear error

There is no synthetic fallback. If FIRMS is unreachable and nothing real has
been fetched before, the run fails loudly instead of inventing detections.
"""
from __future__ import annotations

import geopandas as gpd
import pandas as pd

import config
from src import classify, store
from src.alerts import engine as alert_engine
from src.firms import fetch as firms_fetch
from src.geospatial import landcover, osm, spatial_join
from src.processing import cleaning


def load_hotspots(api_key: str | None = None) -> tuple[pd.DataFrame, str]:
    """LIVE API -> LOCAL CACHE (most recent real raw pull). Raises when neither exists."""
    key = api_key or config.FIRMS_API_KEY
    if key:
        try:
            df = firms_fetch.fetch_hotspots(api_key=key)
            if not df.empty:
                return df, "firms_live"
            print("[pipeline] FIRMS returned no rows, trying the last live pull")
        except firms_fetch.FirmsAuthError as exc:
            print(f"[pipeline] FIRMS auth error: {exc}")
        except Exception as exc:
            print(f"[pipeline] FIRMS fetch failed: {exc}")
    else:
        print("[pipeline] no FIRMS_API_KEY configured")

    cached = sorted(config.RAW_DIR.glob("firms_*.csv"))
    if cached:
        try:
            df = pd.read_csv(cached[-1])
            df["acq_date"] = pd.to_datetime(df["acq_date"])
            return df, "local_cache"
        except Exception as exc:
            print(f"[pipeline] local cache read failed: {exc}")

    raise RuntimeError(
        "No live FIRMS data: the API is unreachable (or FIRMS_API_KEY is missing from .env) "
        "and no previous live pull is cached."
    )


def run_pipeline(api_key: str | None = None, use_osm_cache_first: bool = False) -> dict:
    """Run the full pipeline once on live data and return everything the
    dashboard needs. Raises if no live (or previously fetched live) data exists."""
    raw_df, hotspot_source = load_hotspots(api_key)
    if raw_df.empty:
        raise RuntimeError("FIRMS returned no detections for the region.")

    clean_df, clean_report = cleaning.clean_hotspots(raw_df)
    if clean_df.empty:
        raise RuntimeError("All rows were dropped during data cleaning — check the source data.")

    zones, zone_source = osm.get_industrial_zones(use_cache_first=use_osm_cache_first)
    df = spatial_join.join_zone_type(clean_df, zones)
    df = spatial_join.add_industrial_distances(df, zones)

    landcover_zones, landcover_source = landcover.get_landcover_zones(use_cache_first=use_osm_cache_first)
    df = spatial_join.join_landcover_context(df, landcover_zones)

    detail_df, cluster_df, classify_info = classify.classify_hotspots(df)
    alerts = alert_engine.generate_alerts(detail_df, cluster_df)

    gdf = gpd.GeoDataFrame(detail_df, geometry=gpd.points_from_xy(detail_df["longitude"], detail_df["latitude"]), crs="EPSG:4326")
    export = gdf.copy()
    export["acq_date"] = export["acq_date"].astype(str)
    export.to_file(config.CLASSIFIED_GEOJSON, driver="GeoJSON")
    export.drop(columns="geometry").to_csv(config.CLASSIFIED_CSV, index=False)

    if not cluster_df.empty:
        cluster_export = cluster_df.copy()
        cluster_export["first_detected"] = cluster_export["first_detected"].astype(str)
        cluster_export["last_detected"] = cluster_export["last_detected"].astype(str)
        cluster_export.to_csv(config.PROCESSED_DIR / "cluster_summary.csv", index=False)

    import json
    (config.PROCESSED_DIR / "alerts.json").write_text(json.dumps(alerts, default=str))

    return {
        "detail_gdf": gdf,
        "cluster_df": cluster_df,
        "alerts": alerts,
        "hotspot_source": hotspot_source,
        "zone_source": zone_source,
        "n_industrial_zones": len(zones),
        "landcover_source": landcover_source,
        "n_landcover_zones": len(landcover_zones),
        "clean_report": clean_report,
        "ml_metrics": classify_info["ml_metrics"],
        "n_stored_total": store.count(),
        "run_at": pd.Timestamp.now(),
    }


if __name__ == "__main__":
    info = run_pipeline()
    print(f"source: {info['hotspot_source']} / {info['zone_source']}")
    print(f"detections: {len(info['detail_gdf'])}  clusters: {len(info['cluster_df'])}  alerts: {len(info['alerts'])}")
    print(info["detail_gdf"]["rule_label"].value_counts())
    if info["ml_metrics"].get("trained"):
        print(f"ML accuracy: {info['ml_metrics']['accuracy']:.2f}")
