"""Refresh public global FIRMS feeds without a key, preserving the India export."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import config
from src.planetary.context import refresh_geonames_reference, refresh_wri_reference
from src.planetary.export import DEFAULT_OUTPUT, export_global_payload
from src.planetary.pipeline import run_global_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-events", type=int, default=config.GLOBAL_MAX_EVENTS)
    parser.add_argument("--weather-limit", type=int, default=config.GLOBAL_WEATHER_MAX_EVENTS)
    parser.add_argument("--refresh-references", "--refresh-reference", action="store_true",
                        help="Download missing or 30-day-old WRI/GeoNames references")
    args = parser.parse_args()
    if args.max_events < 1 or args.weather_limit < 0:
        parser.error("max-events must be positive; weather-limit must be nonnegative")
    if args.refresh_references:
        for name, path, refresh in [("WRI", config.GLOBAL_WRI_PATH, refresh_wri_reference),
                                    ("GeoNames", config.GLOBAL_PLACES_PATH, refresh_geonames_reference)]:
            if path.exists() and time.time() - path.stat().st_mtime < 30 * 86400:
                continue
            try:
                refresh()
            except Exception as exc:
                print(f"{name} reference update failed; continuing with available context: {exc}")
    try:
        payload = run_global_pipeline(max_events=args.max_events, weather_limit=args.weather_limit)
        path = export_global_payload(payload, args.output)
    except Exception as exc:
        print(f"Global refresh failed; previous export retained: {exc}", file=sys.stderr)
        return 1
    meta = payload["meta"]
    print(f"Global export: {path}; {meta['observations']} observations, {meta['globalActiveHotspots']} cells, "
          f"{meta['events']} exported events, {meta['weatherEnrichedEvents']} weather enrichments; partial={meta['partial']}")
    for feed in meta["feeds"]:
        print(f"  {feed['source']}: {feed['status']} ({feed['observations']} observations)")
    if meta["partial"]:
        print("::warning::Global coverage is partial or sampled; consult global-events.json metadata.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
