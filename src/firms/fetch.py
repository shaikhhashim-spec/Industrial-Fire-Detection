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


def _redact(text: str, api_key: str | None) -> str:
    """FIRMS puts the key in the request URL itself, so any exception raised
    by `requests` (timeouts, HTTP errors, connection failures) echoes it back
    in the message. Strip it before the text can reach a log, console, or —
    worse — an uncaught exception rendered straight into the Streamlit UI."""
    if not api_key:
        return text
    return text.replace(api_key, "***REDACTED***")


def check_map_key(api_key: str | None = None) -> dict:
    """Validate a key against FIRMS's own status endpoint before spending
    fetch quota on it. Raises FirmsAuthError if invalid/missing/unreachable —
    always redacted, and always this type, so a caller that only catches
    FirmsAuthError never sees a raw, key-bearing traceback."""
    api_key = api_key or config.FIRMS_API_KEY
    if not api_key:
        raise FirmsAuthError("No FIRMS_API_KEY configured. Set it in .env — see .env.example.")
    try:
        resp = requests.get(config.FIRMS_STATUS_URL, params={"MAP_KEY": api_key}, timeout=30)
        resp.raise_for_status()
    except requests.exceptions.RequestException as exc:
        raise FirmsAuthError(f"Could not reach FIRMS to validate the key: {_redact(str(exc), api_key)}") from None
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
            last_error = _redact(str(exc), api_key)
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
                print(f"[firms.fetch] {source} {end_date}: {_redact(str(exc), api_key)}")
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


def _fetch_bbox(source: str, day_range: int, end_date: str, api_key: str, bbox: dict) -> list[pd.DataFrame]:
    """One area/csv request for the whole bbox; only if that fails, the same
    window as <=8x8-degree tiles. A whole-India bbox in a single request was
    verified to work (2026-09-11), so tiling is now the fallback, not the
    default — it was 16x the requests per source."""
    area = f"{bbox['min_lon']},{bbox['min_lat']},{bbox['max_lon']},{bbox['max_lat']}"
    try:
        return [_fetch_chunk(source, day_range, end_date, api_key, area=area)]
    except FirmsAuthError:
        raise
    except Exception as exc:
        print(f"[firms.fetch] national {source} whole-bbox: {_redact(str(exc), api_key)} — tiling")
    frames = []
    for tile in _tile_bbox(bbox):
        try:
            frames.append(_fetch_chunk(source, day_range, end_date, api_key, area=tile))
        except FirmsAuthError:
            raise
        except Exception as exc:
            print(f"[firms.fetch] national {source} tile {tile}: {_redact(str(exc), api_key)}")
    return frames


def fetch_country_hotspots(
    country: str = "IND",
    sources: list[str] | None = None,
    day_range: int | None = None,
    api_key: str | None = None,
    fallback_bbox: dict | None = None,
    total_days: int | None = None,
) -> pd.DataFrame:
    """National-scale fetch across the country's bounding box.

    FIRMS's country/csv endpoint is no longer attempted: it answers HTTP 400
    "Invalid API call" for every source (re-verified 2026-09-11), and each
    attempt burned FIRMS_MAX_RETRIES backoff sleeps before falling through.
    Country clipping happens downstream instead, against real state
    boundaries (src/national/states.py), which also drops offshore and
    cross-border detections the bbox necessarily includes.

    By default pulls the latest `day_range` days (the per-run refresh).
    `total_days` backfills a longer window in FIRMS_CHUNK_DAYS requests —
    used once to seed persistence history when the national store is cold.
    """
    sources = sources or config.NATIONAL_FIRMS_SOURCES
    day_range = day_range or config.NATIONAL_DAY_RANGE
    total_days = total_days or day_range
    bbox = fallback_bbox or config.INDIA_BBOX
    api_key = api_key or config.FIRMS_API_KEY
    if not api_key:
        raise FirmsAuthError("No FIRMS_API_KEY configured. Set it in .env — see .env.example.")

    import datetime as dt

    frames = []
    end = dt.date.today()
    remaining = total_days
    while remaining > 0:
        chunk_days = min(config.FIRMS_CHUNK_DAYS, remaining)
        for source in sources:
            for chunk in _fetch_bbox(source, chunk_days, end.isoformat(), api_key, bbox):
                if not chunk.empty:
                    chunk = chunk.copy()
                    chunk["source"] = source
                    frames.append(chunk)
        end -= dt.timedelta(days=chunk_days)
        remaining -= chunk_days

    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    dedupe_keys = [k for k in ["latitude", "longitude", "acq_date", "acq_time", "satellite"] if k in df.columns]
    df = df.drop_duplicates(subset=dedupe_keys)
    df["acq_date"] = pd.to_datetime(df["acq_date"])
    return df.reset_index(drop=True)
