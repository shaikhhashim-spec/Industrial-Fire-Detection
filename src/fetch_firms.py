"""Fetch NASA FIRMS active-fire/thermal-hotspot data for the target bounding box.

FIRMS area API doc: https://firms.modaps.eosdis.nasa.gov/api/area/
A single request returns at most FIRMS_CHUNK_DAYS (<=10) days of history ending
on a given date, so pulling FIRMS_TOTAL_DAYS of history means looping backwards
in chunks and concatenating the results.
"""
from __future__ import annotations

import datetime as dt
import io

import pandas as pd
import requests

import config

DEDUPE_KEYS = ["latitude", "longitude", "acq_date", "acq_time", "satellite"]


class FirmsKeyError(RuntimeError):
    """Raised when the FIRMS_MAP_KEY is missing or rejected by the API."""


def check_map_key(map_key: str | None = None) -> dict:
    """Return FIRMS quota/status info for a MAP_KEY, or raise FirmsKeyError."""
    map_key = map_key or config.FIRMS_MAP_KEY
    if not map_key:
        raise FirmsKeyError("No FIRMS_MAP_KEY configured (set it in .env).")
    resp = requests.get(config.FIRMS_STATUS_URL, params={"MAP_KEY": map_key}, timeout=30)
    resp.raise_for_status()
    text = resp.text.strip()
    if "Invalid" in text or "error" in text.lower():
        raise FirmsKeyError(f"FIRMS rejected MAP_KEY: {text}")
    return {"raw": text}


def _fetch_chunk(source: str, end_date: dt.date, day_range: int, map_key: str) -> pd.DataFrame:
    url = f"{config.FIRMS_BASE_URL}/{map_key}/{source}/{config.FIRMS_AREA_STR}/{day_range}/{end_date.isoformat()}"
    resp = requests.get(url, timeout=60)
    resp.raise_for_status()
    text = resp.text
    if text.startswith("Invalid") or "<html" in text.lower():
        raise FirmsKeyError(f"FIRMS API error for source={source}: {text[:200]}")
    df = pd.read_csv(io.StringIO(text))
    if not df.empty:
        df["source"] = source
    return df


def fetch_hotspots(
    sources: list[str] | None = None,
    total_days: int | None = None,
    map_key: str | None = None,
) -> pd.DataFrame:
    """Pull `total_days` of hotspot history across all `sources`, deduped.

    Raises FirmsKeyError if no key is configured or the API rejects it.
    Caller is expected to fall back to sample data on failure.
    """
    sources = sources or config.FIRMS_SOURCES
    total_days = total_days or config.FIRMS_TOTAL_DAYS
    map_key = map_key or config.FIRMS_MAP_KEY
    if not map_key:
        raise FirmsKeyError("No FIRMS_MAP_KEY configured (set it in .env).")

    frames = []
    today = dt.date.today()
    remaining = total_days
    end_date = today
    while remaining > 0:
        day_range = min(config.FIRMS_CHUNK_DAYS, remaining)
        for source in sources:
            try:
                chunk = _fetch_chunk(source, end_date, day_range, map_key)
                if not chunk.empty:
                    frames.append(chunk)
            except FirmsKeyError:
                raise
            except Exception as exc:  # network hiccup on one chunk shouldn't kill the pull
                print(f"[fetch_firms] warning: {source} {end_date} failed: {exc}")
        end_date -= dt.timedelta(days=day_range)
        remaining -= day_range

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset=[k for k in DEDUPE_KEYS if k in df.columns])
    df["acq_date"] = pd.to_datetime(df["acq_date"])

    raw_path = config.RAW_DIR / f"firms_{today.isoformat()}.csv"
    df.to_csv(raw_path, index=False)
    return df.reset_index(drop=True)


if __name__ == "__main__":
    data = fetch_hotspots()
    print(f"Fetched {len(data)} hotspots across {config.FIRMS_TOTAL_DAYS} days")
    print(data.head())
