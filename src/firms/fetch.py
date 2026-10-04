"""NASA FIRMS hotspot fetch: retries with backoff, a TTL cache with
stale-cache fallback if the network is down entirely, and detection of
FIRMS's "HTTP 200 but a plain-text error body" failure mode — which a naive
`pd.read_csv` would otherwise silently mis-parse.

FIRMS_API_KEY is read from the environment (.env), never hard-coded. See
.env.example.
"""
from __future__ import annotations

import io
import datetime as dt
import os
import tempfile
import time
from pathlib import Path

import pandas as pd
import requests

import config


def _parse_global_csv(text: str) -> pd.DataFrame:
    """Reject HTML/error/truncated schemas before replacing a usable cache."""
    df = pd.read_csv(io.StringIO(text), dtype={"acq_time": str})
    required = {"latitude", "longitude", "acq_date", "acq_time", "frp", "confidence", "satellite"}
    if not required.issubset(df.columns):
        raise FirmsAPIError("Global FIRMS response lacks required observation columns")
    if not df.empty:
        lat = pd.to_numeric(df.latitude, errors="coerce")
        lon = pd.to_numeric(df.longitude, errors="coerce")
        frp = pd.to_numeric(df.frp, errors="coerce")
        date = pd.to_datetime(df.acq_date, errors="coerce", utc=True)
        valid = lat.between(-90, 90) & lon.between(-180, 180) & frp.between(0, float("inf"), inclusive="left") & date.notna()
        if not valid.any():
            raise FirmsAPIError("Global FIRMS response contains no valid observation rows")
    return df


def _download_global_csv(url: str) -> str:
    # Streaming enforces a bound even for chunked or compressed responses.
    with requests.get(url, timeout=(10, 90), stream=True) as response:
        response.raise_for_status()
        chunks, size = [], 0
        for chunk in response.iter_content(chunk_size=65536):
            size += len(chunk)
            if size > config.GLOBAL_FIRMS_MAX_BYTES:
                raise FirmsAPIError("Global FIRMS response exceeded the configured byte limit")
            chunks.append(chunk)
    return b"".join(chunks).decode("utf-8-sig")


def _atomic_cache_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as file:
            temporary = Path(file.name)
            file.write(text)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def fetch_global_hotspots(
    sources: list[str] | None = None, window_hours: int = config.GLOBAL_FIRMS_WINDOW_HOURS,
    *, force: bool = False,
) -> pd.DataFrame:
    """Public VIIRS global 24/48h feeds, with bounded retries/cache age.

    No regional tiling and no key. Failed sensors remain visible in attrs;
    no usable sensors raises rather than substituting synthetic observations.
    Cache timestamps describe retrieval, not satellite acquisition freshness.
    """
    if window_hours not in (24, 48):
        raise ValueError("Global FIRMS window must be 24 or 48 hours")
    sources = list(config.GLOBAL_FIRMS_FEEDS) if sources is None else sources
    if not sources or any(source not in config.GLOBAL_FIRMS_FEEDS for source in sources):
        raise ValueError("Select at least one supported global VIIRS source")
    frames, feeds = [], []
    for source in dict.fromkeys(sources):
        directory, prefix = config.GLOBAL_FIRMS_FEEDS[source]
        url = f"https://firms.modaps.eosdis.nasa.gov/data/active_fire/{directory}/csv/{prefix}_Global_{window_hours}h.csv"
        cache = config.CACHE_DIR / f"firms_global_{source}_{window_hours}h.csv"
        cached, age = None, float("inf")
        if cache.exists():
            age = max(0, (time.time() - cache.stat().st_mtime) / 3600)
            if age <= config.GLOBAL_FIRMS_STALE_MAX_HOURS and cache.stat().st_size <= config.GLOBAL_FIRMS_MAX_BYTES:
                try:
                    cached = _parse_global_csv(cache.read_text(encoding="utf-8"))
                except (OSError, ValueError, pd.errors.ParserError, FirmsAPIError):
                    pass
        state, error, frame = "unavailable", None, None
        if cached is not None and age < config.FIRMS_CACHE_TTL_HOURS and not force:
            frame, state = cached, "cache"
        else:
            for attempt in range(2):
                try:
                    body = _download_global_csv(url)
                    candidate = _parse_global_csv(body)
                    _atomic_cache_text(cache, body)
                    frame = candidate
                    state, age = "live", 0.0
                    break
                except (requests.RequestException, ValueError, OSError, pd.errors.ParserError, FirmsAPIError) as exc:
                    error = str(exc)[:300]
                    if attempt == 0:
                        time.sleep(config.FIRMS_BACKOFF_FACTOR)
            if frame is None and cached is not None:
                frame, state = cached, "stale_cache"
        record = {"source": source, "url": url, "status": state,
                  "retrievedAt": dt.datetime.fromtimestamp(cache.stat().st_mtime, dt.timezone.utc).isoformat()
                  if frame is not None else None,
                  "cacheAgeHours": round(age, 2) if frame is not None else None,
                  "observations": len(frame) if frame is not None else 0}
        if state in ("unavailable", "stale_cache"):
            record["error"] = error or "No usable recent cache"
        feeds.append(record)
        if frame is not None:
            frame = frame.copy()
            frame["source"] = source
            frames.append(frame)
    if not frames:
        raise FirmsAPIError("No usable global FIRMS feeds; previous global export was not replaced")
    result = pd.concat(frames, ignore_index=True).drop_duplicates(
        subset=["latitude", "longitude", "acq_date", "acq_time", "satellite"])
    result.attrs.update(feeds=feeds, window_hours=window_hours,
                        partial=any(feed["status"] in ("unavailable", "stale_cache") for feed in feeds),
                        source="firms_live" if all(feed["status"] == "live" for feed in feeds) else "local_cache")
    return result.reset_index(drop=True)


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
            try:
                df = _parse_global_csv(cache_file.read_text(encoding="utf-8"))
                df.attrs["source"] = "local_cache"
                return df
            except (OSError, ValueError, FirmsAPIError):
                pass

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
            df = _parse_global_csv(resp.text)
            _atomic_cache_text(cache_file, resp.text)
            df.attrs["source"] = "firms_live"
            return df
        except FirmsAuthError:
            raise
        except (requests.exceptions.RequestException, FirmsAPIError, ValueError, OSError) as exc:
            last_error = _redact(str(exc), api_key)
            if attempt < config.FIRMS_MAX_RETRIES:
                time.sleep(config.FIRMS_BACKOFF_FACTOR ** attempt)

    if cache_file.exists():
        try:
            df = _parse_global_csv(cache_file.read_text(encoding="utf-8"))
            df.attrs["stale_cache_fallback"] = True
            df.attrs["source"] = "local_cache"
            return df
        except (OSError, ValueError, FirmsAPIError):
            pass
    raise FirmsAPIError(f"{source}: all {config.FIRMS_MAX_RETRIES} attempts failed ({last_error}), no cache available")


def fetch_hotspots(
    sources: list[str] | None = None,
    total_days: int | None = None,
    api_key: str | None = None,
) -> pd.DataFrame:
    """Pull `total_days` of history across all `sources` for the target
    bbox, deduped. Raises FirmsAuthError if no key/an invalid key is
    configured; caller should fall back to cached real observations."""
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
    origins = {frame.attrs.get("source", "firms_live") for frame in frames}
    df.attrs["source"] = next(iter(origins)) if len(origins) == 1 else "mixed"

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
    origins = {frame.attrs.get("source", "firms_live") for frame in frames}
    df.attrs["source"] = next(iter(origins)) if len(origins) == 1 else "mixed"
    return df.reset_index(drop=True)
