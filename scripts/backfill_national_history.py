"""Optional, one-time offline seed for the national historical store.

Pulls the last N days of India-wide FIRMS data — chunked into <=5-day
windows (this key's tier caps a single request's day_range at 5), tiled
across ~16 sub-boxes covering India, across all 3 VIIRS sources
(S-NPP/NOAA-20/NOAA-21) — and merges it into the persistent national store
(src/national/store.py) that the live app's incremental pipeline also
writes to on every run.

Deliberately NOT wired into the live Streamlit app as a button: a full
30-day backfill is on the order of a few hundred sequential HTTP requests
(day-chunks x tiles x sources) and can take several minutes with the
occasional transient failure — fine to run once from a terminal ahead of
a demo, risky as an interactive in-app action a judge might click and
wait on mid-presentation. Safe to re-run any time; every row upserts by
its natural key, so nothing gets duplicated.

Usage:
    python scripts/backfill_national_history.py
    python scripts/backfill_national_history.py --days 14
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from src.firms.fetch import FirmsAuthError, _fetch_chunk, _tile_bbox  # noqa: E402
from src.ml.rules import normalize_confidence  # noqa: E402
from src.national import states as national_states  # noqa: E402
from src.national import store as national_store  # noqa: E402
from src.processing import cleaning  # noqa: E402


def backfill(days: int = config.NATIONAL_HISTORY_DAYS, api_key: str | None = None) -> None:
    api_key = api_key or config.FIRMS_API_KEY
    if not api_key:
        print("No FIRMS_API_KEY configured (.env) — aborting.")
        return

    tiles = _tile_bbox(config.INDIA_BBOX)
    chunk_days = config.FIRMS_CHUNK_DAYS
    today = dt.date.today()
    n_chunks = (days + chunk_days - 1) // chunk_days
    total_requests = n_chunks * len(tiles) * len(config.NATIONAL_FIRMS_SOURCES)

    print(f"Backfilling {days} day(s) of India-wide FIRMS history: {n_chunks} day-chunk(s) x "
          f"{len(tiles)} tiles x {len(config.NATIONAL_FIRMS_SOURCES)} sources "
          f"= up to {total_requests} requests. This will take a while.\n")

    total_rows = 0
    t0 = time.time()
    for chunk_i in range(n_chunks):
        end_date = (today - dt.timedelta(days=chunk_i * chunk_days)).isoformat()
        this_chunk_days = min(chunk_days, days - chunk_i * chunk_days)
        for source in config.NATIONAL_FIRMS_SOURCES:
            for tile in tiles:
                try:
                    df = _fetch_chunk(source, this_chunk_days, end_date, api_key, area=tile)
                except FirmsAuthError as exc:
                    print(f"AUTH ERROR — aborting: {exc}")
                    return
                except Exception as exc:
                    print(f"  [{source} {tile} ending {end_date}] failed, skipping: {exc}")
                    continue
                if df.empty:
                    continue
                df = df.copy()
                df["source"] = source
                clean_df, _ = cleaning.clean_hotspots(df, bbox={})
                if clean_df.empty:
                    continue
                clean_df = normalize_confidence(clean_df)
                clean_df = national_states.assign_state(clean_df)
                national_store.upsert(clean_df)
                total_rows += len(clean_df)
        print(f"  chunk ending {end_date}: {total_rows} rows accumulated so far "
              f"({round(time.time() - t0)}s elapsed)")

    print(f"\nDone in {round(time.time() - t0)}s — {national_store.count()} total rows now in the store, "
          f"covering {national_store.days_covered()} distinct day(s).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--days", type=int, default=config.NATIONAL_HISTORY_DAYS,
                         help=f"How many days of history to backfill (default: {config.NATIONAL_HISTORY_DAYS}).")
    args = parser.parse_args()
    backfill(days=args.days)
