"""Run the national pipeline on live FIRMS data and export it to the 3D globe.

Same steps as Settings, Run pipeline in the Streamlit app (India view), but
from the command line, handy for refreshing holo-view-maker/public/data/
events.json on a schedule or before a demo.

Usage:  .venv\\Scripts\\python scripts\\refresh_national_globe.py
"""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config
from src.national.pipeline import run_national_pipeline
from src.national.states import load_states
from src.utils.export_3d_globe import export_pipeline_events_for_holo_view


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        info = run_national_pipeline()
    except RuntimeError as exc:
        print(f"Refresh failed: {exc}")
        return 1
    source = info["hotspot_source"]
    print(f"source: {source}  observations: {info['n_observations']}  events: {info['n_events']}  "
          f"history days: {info['history_days_covered']}  dropped outside India: {info['dropped_outside_india']}")
    events = export_pipeline_events_for_holo_view(events_df=info["events_df"], national_detail_df=info["detail_df"])

    # sanity: every exported point must sit inside an Indian state/UT polygon
    import geopandas as gpd

    states = load_states()
    pts = gpd.GeoDataFrame(geometry=gpd.points_from_xy([e["longitude"] for e in events],
                                                       [e["latitude"] for e in events]), crs="EPSG:4326")
    inside = gpd.sjoin(pts, states[["geometry"]], how="left", predicate="within")["index_right"].notna()
    inside = inside[~inside.index.duplicated()]
    print(f"exported {len(events)} events; inside India: {int(inside.sum())}/{len(events)}")
    print("categories:", dict(Counter(e["category"] for e in events).most_common()))
    with_fac = [e for e in events if e.get("facility")]
    print(f"attributed to a known facility within 3 km: {len(with_fac)} "
          f"({len(with_fac) / max(1, len(events)):.0%}); kinds: "
          f"{dict(Counter(e['facility']['kind'] for e in with_fac).most_common(6))}")
    for e in events[:2]:
        print(f"\n{e['id']}, {e['region']}, {e['category']} (risk {e['riskScore']})")
        for r in e["reasons"]:
            print("   •", r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
