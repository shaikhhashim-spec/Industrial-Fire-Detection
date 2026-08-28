"""NASA FIRMS hotspot fetch: retries with backoff, a TTL cache with
stale-cache fallback if the network is down entirely, and detection of
FIRMS's "HTTP 200 but a plain-text error body" failure mode — which a naive
`pd.read_csv` would otherwise silently mis-parse.

FIRMS_API_KEY is read from the environment (.env), never hard-coded. See
.env.example.
"""
from __future__ import annotations

import io
import time
from pathlib import Path

import pandas as pd
import requests

import config


class FirmsAuthError(RuntimeError):
    """Missing/invalid/exhausted MAP_KEY. Not retried — retrying a bad key
    just burns the transaction quota for nothing."""


class FirmsAPIError(RuntimeError):
    """Transient failure, or no cache available to fall back to."""


def check_map_key(api_key: str | None = None) -> dict:
    """Validate a key against FIRMS's own status endpoint before spending
    fetch quota on it. Raises FirmsAuthError if invalid/missing."""
    api_key = api_key or config.FIRMS_API_KEY
    if not api_key:
        raise FirmsAuthError("No FIRMS_API_KEY configured. Set it in .env — see .env.example.")
    resp = requests.get(config.FIRMS_STATUS_URL, params={"MAP_KEY": api_key}, timeout=30)
    resp.raise_for_status()
    text = resp.text.strip()
    if "invalid" in text.lower():
        raise FirmsAuthError(f"FIRMS rejected this key: {text}")
    return {"raw": text}


def _looks_like_error_payload(text: str) -> str | None:
    stripped = text.strip()
    if not stripped:
        return "Empty response body"
    first_line = stripped.splitlines()[0].lower()
    error_markers = ("invalid", "error", "exceed", "not found", "unauthorized", "no data")
    header_markers = ("latitude", "country_id")
    if any(m in first_line for m in error_markers) and not any(m in first_line for m in header_markers):
        return stripped[:300]
    return None


def _cache_path(scope: str, source: str, day_range: int, end_date: str) -> Path:
    key = f"firms_{scope}_{source}_{day_range}_{end_date}".replace(",", "-")
    return config.CACHE_DIR / f"{key}.csv"


def _fetch_chunk(
    source: str, day_range: int, end_date: str, api_key: str,
    area: str | None = None, country: str | None = None,
) -> pd.DataFrame:
    """area (bbox 'west,south,east,north') or country (ISO3 code) — exactly
    one of the two. Country queries use FIRMS's dedicated country endpoint,
    which avoids having to tile a large bounding box into multiple requests."""
    # scope must include the actual area/country so distinct tiles (or
    # country vs regional area) never collide on the same cache filename.
    scope = f"country-{country}" if country else f"area-{area or config.FIRMS_AREA_STR}"
    cache_file = _cache_path(scope, source, day_range, end_date)
    if cache_file.exists():
        age_hours = (time.time() - cache_file.stat().st_mtime) / 3600
        if age_hours < config.FIRMS_CACHE_TTL_HOURS:
            return pd.read_csv(cache_file)

    if country:
        url = f"{config.FIRMS_COUNTRY_BASE_URL}/{api_key}/{source}/{country}/{day_range}/{end_date}"
    else:
        url = f"{config.FIRMS_BASE_URL}/{api_key}/{source}/{area or config.FIRMS_AREA_STR}/{day_range}/{end_date}"
    last_error = None
    for attempt in range(1, config.FIRMS_MAX_RETRIES + 1):
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            error_msg = _looks_like_error_payload(resp.text)
            if error_msg:
                if any(m in error_msg.lower() for m in ("invalid", "unauthorized", "exceed")):
                    raise FirmsAuthError(f"FIRMS rejected the request for {source}: {error_msg}")
                raise FirmsAPIError(f"FIRMS returned an error payload for {source}: {error_msg}")
            df = pd.read_csv(io.StringIO(resp.text))
            df.to_csv(cache_file, index=False)
            return df
        except FirmsAuthError:
            raise
        except (requests.exceptions.RequestException, FirmsAPIError, pd.errors.ParserError) as exc:
            last_error = exc
            if attempt < config.FIRMS_MAX_RETRIES:
                time.sleep(config.FIRMS_BACKOFF_FACTOR ** attempt)

    if cache_file.exists():
        df = pd.read_csv(cache_file)
        df.attrs["stale_cache_fallback"] = True
        return df
    raise FirmsAPIError(f"{source}: all {config.FIRMS_MAX_RETRIES} attempts failed ({last_error}), no cache available")


def fetch_hotspots(
    sources: list[str] | None = None,
    total_days: int | None = None,
    api_key: str | None = None,
) -> pd.DataFrame:
    """Pull `total_days` of history across all `sources` for the target
    bbox, deduped. Raises FirmsAuthError if no key/an invalid key is
    configured — caller should fall back to cache/demo data."""
    import datetime as dt

    sources = sources or config.FIRMS_SOURCES
    total_days = total_days or config.FIRMS_TOTAL_DAYS
    api_key = api_key or config.FIRMS_API_KEY
    if not api_key:
        raise FirmsAuthError("No FIRMS_API_KEY configured. Set it in .env — see .env.example.")

    frames = []
    today = dt.date.today()
    remaining = total_days
    end_date = today
    while remaining > 0:
        day_range = min(config.FIRMS_CHUNK_DAYS, remaining)
        for source in sources:
            try:
                chunk = _fetch_chunk(source, day_range, end_date.isoformat(), api_key)
                if not chunk.empty:
                    chunk = chunk.copy()
                    chunk["source"] = source
                    frames.append(chunk)
            except FirmsAuthError:
                raise
            except Exception as exc:
                print(f"[firms.fetch] {source} {end_date}: {exc}")
        end_date -= dt.timedelta(days=day_range)
        remaining -= day_range

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    dedupe_keys = [k for k in ["latitude", "longitude", "acq_date", "acq_time", "satellite"] if k in df.columns]
    df = df.drop_duplicates(subset=dedupe_keys)
    df["acq_date"] = pd.to_datetime(df["acq_date"])

    raw_path = config.RAW_DIR / f"firms_{today.isoformat()}.csv"
    df.to_csv(raw_path, index=False)
    return df.reset_index(drop=True)


def _tile_bbox(bbox: dict, tile_deg: float = 8.0) -> list[str]:
    """Split a large bbox into <=tile_deg x tile_deg sub-boxes as
    'west,south,east,north' strings — FIRMS's area API caps a single
    request's bbox at 10x10 degrees."""
    import numpy as _np

    lons = _np.arange(bbox["min_lon"], bbox["max_lon"], tile_deg)
    lats = _np.arange(bbox["min_lat"], bbox["max_lat"], tile_deg)
    tiles = []
    for lon in lons:
        for lat in lats:
            w, s = lon, lat
            e, n = min(lon + tile_deg, bbox["max_lon"]), min(lat + tile_deg, bbox["max_lat"])
            tiles.append(f"{w:.2f},{s:.2f},{e:.2f},{n:.2f}")
    return tiles


def fetch_country_hotspots(
    country: str = "IND",
    sources: list[str] | None = None,
    day_range: int | None = None,
    api_key: str | None = None,
    fallback_bbox: dict | None = None,
) -> pd.DataFrame:
    """National-scale fetch: latest `day_range` days across the country.

    FIRMS's dedicated country/csv endpoint is attempted first, but was found
    at build time to return "Invalid API call" for every source/country
    tried — including NASA's own documented tutorial example — suggesting
    the service is genuinely unavailable server-side right now, not a bug
    here. Falls back to tiling `fallback_bbox` into <=8x8-degree area/csv
    requests (the endpoint this project has already verified works
    reliably), which is why this is the primary path in practice.

    Deliberately shallow (default 2 days) — this is the "latest
    observations" layer, not a 60-day history pull; see
    src/national/pipeline.py for why repeatedly pulling a long window
    country-wide would be both slow and against FIRMS's fair-use spirit.
    """
    sources = sources or config.NATIONAL_FIRMS_SOURCES
    day_range = day_range or config.NATIONAL_DAY_RANGE
    api_key = api_key or config.FIRMS_API_KEY
    if not api_key:
        raise FirmsAuthError("No FIRMS_API_KEY configured. Set it in .env — see .env.example.")

    import datetime as dt

    end_date = dt.date.today().isoformat()
    frames = []

    for source in sources:
        try:
            chunk = _fetch_chunk(source, day_range, end_date, api_key, country=country)
            if not chunk.empty:
                chunk = chunk.copy()
                chunk["source"] = source
                frames.append(chunk)
        except FirmsAuthError:
            raise
        except Exception as exc:
            print(f"[firms.fetch] national {source} (country endpoint): {exc}")

    if not frames and fallback_bbox:
        tiles = _tile_bbox(fallback_bbox)
        for source in sources:
            for tile in tiles:
                try:
                    chunk = _fetch_chunk(source, day_range, end_date, api_key, area=tile)
                    if not chunk.empty:
                        chunk = chunk.copy()
                        chunk["source"] = source
                        frames.append(chunk)
                except FirmsAuthError:
                    raise
                except Exception as exc:
                    print(f"[firms.fetch] national {source} tile {tile}: {exc}")

    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    dedupe_keys = [k for k in ["latitude", "longitude", "acq_date", "acq_time", "satellite"] if k in df.columns]
    df = df.drop_duplicates(subset=dedupe_keys)
    df["acq_date"] = pd.to_datetime(df["acq_date"])
    return df.reset_index(drop=True)
