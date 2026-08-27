"""End-to-end orchestration: fetch -> persistence -> OSM join -> rule score
-> ML layer -> save output for the dashboard.

Falls back to synthetic sample data / cached OSM zones whenever a live
source is unavailable (no FIRMS key yet, Overpass down, offline demo, etc.)
so the app always has something to show.
"""
from __future__ import annotations

import geopandas as gpd
import pandas as pd

import config
from src import fetch_firms, ml_model, osm_industrial, persistence, sample_data, scoring, zone_join


def load_hotspots(map_key: str | None = None) -> tuple[pd.DataFrame, str]:
    """Return (df, source_label) where source_label is 'firms_live' or 'sample_data'."""
    key = map_key or config.FIRMS_MAP_KEY
    if key:
        try:
            df = fetch_firms.fetch_hotspots(map_key=key)
            if not df.empty:
                return df, "firms_live"
            print("[pipeline] FIRMS returned no rows, falling back to sample data")
        except fetch_firms.FirmsKeyError as exc:
            print(f"[pipeline] FIRMS key error: {exc}")
        except Exception as exc:
            print(f"[pipeline] FIRMS fetch failed: {exc}")
    else:
        print("[pipeline] no FIRMS_MAP_KEY configured, using sample data")

    return sample_data.generate_sample_hotspots(), "sample_data"


def run_pipeline(map_key: str | None = None, use_osm_cache_first: bool = False) -> tuple[gpd.GeoDataFrame, dict]:
    """Run the full pipeline and write output/classified_hotspots.(geojson|csv).

    Returns (geodataframe, run_info) where run_info carries data-source
    labels and ML metrics for display in the dashboard.
    """
    df, hotspot_source = load_hotspots(map_key)
    if df.empty:
        raise RuntimeError("No hotspot data available from any source (live or sample).")

    df = persistence.compute_persistence(df)

    zones, zone_source = osm_industrial.get_industrial_zones(use_cache_first=use_osm_cache_first)
    df = zone_join.join_zone_type(df, zones)

    df = scoring.classify(df)
    df, ml_metrics = ml_model.train_and_predict(df)

    gdf = gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df["longitude"], df["latitude"]),
        crs="EPSG:4326",
    )
    gdf["acq_date"] = gdf["acq_date"].astype(str)

    gdf.to_file(config.CLASSIFIED_GEOJSON, driver="GeoJSON")
    gdf.drop(columns="geometry").to_csv(config.CLASSIFIED_CSV, index=False)

    run_info = {
        "hotspot_source": hotspot_source,
        "zone_source": zone_source,
        "n_hotspots": len(gdf),
        "n_industrial_zones": len(zones),
        "ml_metrics": ml_metrics,
    }
    return gdf, run_info


if __name__ == "__main__":
    gdf, info = run_pipeline()
    print(f"Pipeline complete: {info['n_hotspots']} hotspots classified")
    print(f"  hotspot source: {info['hotspot_source']}, zone source: {info['zone_source']}")
    print(gdf["rule_label"].value_counts())
    if info["ml_metrics"]["trained"]:
        print(f"ML accuracy: {info['ml_metrics']['accuracy']:.2f}")
        print(f"Feature importances: {info['ml_metrics']['feature_importances']}")
