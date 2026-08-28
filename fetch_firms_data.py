"""
fetch_firms_data.py

Fetches near-real-time / recent-archive fire detection data from NASA FIRMS
(Fire Information for Resource Management System) API, with retry logic and
local caching, and returns a pandas DataFrame ready to hand off downstream.

Setup
-----
1. Register a free MAP_KEY: https://firms.modaps.eosdis.nasa.gov/api/area/
2. Set it as an env var:  export FIRMS_MAP_KEY=your_key_here
   (or pass map_key= explicitly)
3. pip install requests pandas

Quick use
---------
    from fetch_firms_data import fetch_firms_data

    df = fetch_firms_data(
        source="VIIRS_SNPP_NRT",
        day_range=1,
        area_coords="-125,32,-114,42",  # west,south,east,north (CA-ish box)
    )
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import time
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd
import requests

logger = logging.getLogger("firms_fetcher")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

FIRMS_BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api"

# Known sources as of FIRMS API docs. Not exhaustive by design — new sensors
# get added over time, so this is a warning, not a hard gate.
VALID_SOURCES = {
    "MODIS_NRT", "MODIS_SP",
    "VIIRS_SNPP_NRT", "VIIRS_SNPP_SP",
    "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT",
    "LANDSAT_NRT",
}


class FirmsAPIError(Exception):
    """Raised when the FIRMS API returns an error we can't recover from."""


class FirmsAuthError(FirmsAPIError):
    """Raised when the MAP_KEY is missing, invalid, or has exhausted its quota.
    Not retried — retrying a bad key just burns your transaction limit."""


def _cache_path(cache_dir: Path, cache_key: str) -> Path:
    return cache_dir / f"{cache_key}.csv"


def _build_url(
    map_key: str,
    source: str,
    day_range: int,
    *,
    area_coords: Optional[str] = None,
    country_code: Optional[str] = None,
    start_date: Optional[str] = None,
) -> str:
    if area_coords and country_code:
        raise ValueError("Provide either area_coords or country_code, not both.")
    if not area_coords and not country_code:
        raise ValueError(
            "Provide one of area_coords ('west,south,east,north') or country_code (ISO3)."
        )

    if area_coords:
        parts = [FIRMS_BASE_URL, "area", "csv", map_key, source, area_coords, str(day_range)]
    else:
        parts = [FIRMS_BASE_URL, "country", "csv", map_key, source, country_code, str(day_range)]

    if start_date:
        parts.append(start_date)

    return "/".join(parts)


def _looks_like_error_payload(text: str) -> Optional[str]:
    """
    FIRMS often returns HTTP 200 even on error conditions (invalid key, bad
    query, quota exceeded) — the body is a short plain-text message instead
    of CSV. Catch that here so it's never silently cached as 'zero fires'.
    """
    stripped = text.strip()
    if not stripped:
        return "Empty response body"
    first_line = stripped.splitlines()[0].lower()
    error_markers = ("invalid", "error", "exceed", "not found", "unauthorized", "no data")
    header_markers = ("latitude", "country_id")  # fragments of a real CSV header
    if any(m in first_line for m in error_markers) and not any(m in first_line for m in header_markers):
        return stripped[:300]
    return None


def _add_detection_id(df: pd.DataFrame) -> pd.DataFrame:
    """
    Attach a short, stable id per detection (hash of lat/lon/date/time) so
    downstream steps — dedup, joins with OSM/land-cover, GIS storage — have
    a reliable key instead of re-deriving one differently each time.
    """
    id_cols = [c for c in ("latitude", "longitude", "acq_date", "acq_time") if c in df.columns]
    if not id_cols:
        return df
    df = df.copy()
    key = df[id_cols].astype(str).agg("_".join, axis=1)
    df["detection_id"] = key.apply(lambda s: hashlib.sha1(s.encode()).hexdigest()[:12])
    return df


def fetch_firms_data(
    source: str,
    day_range: int = 1,
    *,
    area_coords: Optional[str] = None,
    country_code: Optional[str] = None,
    start_date: Optional[str] = None,
    map_key: Optional[str] = None,
    cache_dir: str = ".cache/firms",
    use_cache: bool = True,
    cache_ttl_hours: float = 6.0,
    max_retries: int = 4,
    backoff_factor: float = 1.5,
    timeout: float = 30.0,
) -> pd.DataFrame:
    """
    Fetch fire detection data from the NASA FIRMS API and return it as a
    pandas DataFrame.

    Parameters
    ----------
    source : str
        Sensor/source, e.g. "VIIRS_SNPP_NRT", "MODIS_NRT". See VALID_SOURCES.
    day_range : int
        Number of days of data to pull (1-10 for NRT sources).
    area_coords : str, optional
        Bounding box "west,south,east,north" in decimal degrees.
        Mutually exclusive with country_code.
    country_code : str, optional
        ISO3 country code (e.g. "USA"). Mutually exclusive with area_coords.
    start_date : str, optional
        'YYYY-MM-DD'. Defaults to most recent available data if omitted.
    map_key : str, optional
        Your FIRMS MAP_KEY. Falls back to the FIRMS_MAP_KEY env var.
    cache_dir : str
        Local directory for cached CSV responses (the "local backup copy").
    use_cache : bool
        If True: serve a fresh-enough cache without hitting the network, and
        fall back to a stale cache if every network attempt fails.
    cache_ttl_hours : float
        How long a cached response counts as "fresh" before re-fetching.
    max_retries : int
        Attempts for transient failures (timeouts, connection errors, 5xx).
    backoff_factor : float
        Exponential backoff base; sleep = backoff_factor ** attempt.
    timeout : float
        Per-request timeout in seconds.

    Returns
    -------
    pd.DataFrame
        One row per fire detection. Typical columns: latitude, longitude,
        brightness, scan, track, acq_date, acq_time, satellite, confidence,
        version, bright_t31, frp, daynight (exact columns vary by source).
        If returned via the stale-cache fallback, df.attrs["stale_cache_fallback"]
        is True — check this before handing off if freshness matters downstream.

    Raises
    ------
    FirmsAuthError
        MAP_KEY missing/invalid/exhausted, and no usable cache exists.
    FirmsAPIError
        All retries failed and no usable cache exists.
    """
    map_key = map_key or os.environ.get("FIRMS_MAP_KEY")
    if not map_key:
        raise FirmsAuthError(
            "No FIRMS MAP_KEY provided. Register one at "
            "https://firms.modaps.eosdis.nasa.gov/api/area/ and pass it via "
            "map_key= or the FIRMS_MAP_KEY environment variable."
        )

    if source not in VALID_SOURCES:
        logger.warning(
            "Source '%s' isn't in the known list (%s). Proceeding anyway in "
            "case FIRMS added a new sensor.", source, ", ".join(sorted(VALID_SOURCES))
        )

    url = _build_url(
        map_key, source, day_range,
        area_coords=area_coords, country_code=country_code, start_date=start_date,
    )

    cache_dir_path = Path(cache_dir)
    cache_dir_path.mkdir(parents=True, exist_ok=True)
    cache_key = "_".join(filter(None, [source, str(day_range), area_coords, country_code, start_date]))
    cache_key = cache_key.replace(",", "-").replace("/", "-")
    cache_file = _cache_path(cache_dir_path, cache_key)

    # Serve fresh-enough cache without touching the network.
    if use_cache and cache_file.exists():
        age_hours = (time.time() - cache_file.stat().st_mtime) / 3600
        if age_hours < cache_ttl_hours:
            logger.info("Using local cache (%.1fh old): %s", age_hours, cache_file)
            return _add_detection_id(pd.read_csv(cache_file))

    last_error: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            logger.info("Fetching FIRMS data (attempt %d/%d): %s", attempt, max_retries, url)
            response = requests.get(url, timeout=timeout)
            response.raise_for_status()

            error_msg = _looks_like_error_payload(response.text)
            if error_msg:
                if any(m in error_msg.lower() for m in ("invalid", "unauthorized", "exceed")):
                    raise FirmsAuthError(f"FIRMS API rejected the request: {error_msg}")
                raise FirmsAPIError(f"FIRMS API returned an error payload: {error_msg}")

            df = pd.read_csv(io.StringIO(response.text))
            df = _add_detection_id(df)

            # Write-through cache on every successful fetch — this is the
            # "local backup copy" the Backend/Geospatial handoff can rely on.
            df.to_csv(cache_file, index=False)
            logger.info("Fetched %d rows; cached to %s", len(df), cache_file)
            return df

        except FirmsAuthError:
            raise  # not retryable — bad key, don't burn attempts
        except (requests.exceptions.RequestException, FirmsAPIError, pd.errors.ParserError) as exc:
            last_error = exc
            if attempt < max_retries:
                sleep_s = backoff_factor ** attempt
                logger.warning("Attempt %d failed (%s); retrying in %.1fs", attempt, exc, sleep_s)
                time.sleep(sleep_s)
            else:
                logger.error("All %d attempts failed: %s", max_retries, exc)

    # All retries exhausted — fall back to any cached copy, however stale.
    if use_cache and cache_file.exists():
        logger.warning("Falling back to stale cache after fetch failures: %s", cache_file)
        df = _add_detection_id(pd.read_csv(cache_file))
        df.attrs["stale_cache_fallback"] = True
        return df

    raise FirmsAPIError(
        f"Failed to fetch FIRMS data after {max_retries} attempts and no cache "
        f"was available. Last error: {last_error}"
    )


def fetch_multi_source(
    sources: Iterable[str],
    day_range: int = 1,
    *,
    area_coords: Optional[str] = None,
    country_code: Optional[str] = None,
    start_date: Optional[str] = None,
    map_key: Optional[str] = None,
    cache_dir: str = ".cache/firms",
    use_cache: bool = True,
    cache_ttl_hours: float = 6.0,
    max_retries: int = 4,
    backoff_factor: float = 1.5,
    timeout: float = 30.0,
) -> pd.DataFrame:
    """
    Fetch the same area/window from several sensors (e.g. VIIRS + MODIS) and
    concatenate into one DataFrame, tagged with a 'query_source' column.

    Different sensors have different resolution and revisit times — combining
    them gives denser coverage, which matters for spotting persistent
    industrial heat sources that a single pass might miss. Each source is
    fetched (and cached) independently via fetch_firms_data, so a failure on
    one source doesn't take down the others — this simply propagates whatever
    exception the first failing source raises, after any that succeeded are
    still cached individually for next time.
    """
    frames = []
    for source in sources:
        df = fetch_firms_data(
            source, day_range,
            area_coords=area_coords, country_code=country_code, start_date=start_date,
            map_key=map_key, cache_dir=cache_dir, use_cache=use_cache,
            cache_ttl_hours=cache_ttl_hours, max_retries=max_retries,
            backoff_factor=backoff_factor, timeout=timeout,
        )
        df = df.copy()
        df["query_source"] = source
        frames.append(df)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)


def add_persistence_flags(
    df: pd.DataFrame,
    cluster_radius_km: float = 1.0,
    min_distinct_days: int = 3,
) -> pd.DataFrame:
    """
    Flag detections that recur at roughly the same location across multiple
    distinct days within the fetched window. Industrial heat sources (flares,
    steel plants, power stations) tend to show up repeatedly at a fixed spot;
    a single wildfire event typically doesn't.

    This does NOT classify anything — it only computes a recurrence signal
    that a downstream classifier or GIS layer can use as a feature. Fetch
    with a wider day_range (FIRMS NRT supports up to 10) for this to be
    meaningful; a 1-day fetch can never show recurrence.

    Adds columns:
        cluster_id             -- coarse spatial grid cell id
        cluster_distinct_days  -- distinct acq_date values seen in that cell
        is_persistent_source   -- True if cluster_distinct_days >= min_distinct_days
    """
    df = df.copy()
    if df.empty or "acq_date" not in df.columns:
        df["cluster_id"] = pd.Series(dtype="object")
        df["cluster_distinct_days"] = pd.Series(dtype="int")
        df["is_persistent_source"] = pd.Series(dtype="bool")
        return df

    # Coarse km-based grid snap: 1 deg latitude ~= 111km everywhere; degrees
    # per km of longitude shrinks with cos(latitude). This is a cheap proxy
    # for spatial clustering, not a precise geodesic calculation.
    lat_deg_per_km = 1 / 111.0
    lat_bin = (df["latitude"] / (cluster_radius_km * lat_deg_per_km)).round().astype(int)
    lon_deg_per_km = 1 / (111.0 * np.cos(np.radians(df["latitude"].clip(-89, 89))))
    lon_bin = (df["longitude"] / (cluster_radius_km * lon_deg_per_km)).round().astype(int)
    df["cluster_id"] = lat_bin.astype(str) + "_" + lon_bin.astype(str)

    days_per_cluster = df.groupby("cluster_id")["acq_date"].nunique().rename("cluster_distinct_days")
    df = df.merge(days_per_cluster, on="cluster_id", how="left")
    df["is_persistent_source"] = df["cluster_distinct_days"] >= min_distinct_days
    return df


if __name__ == "__main__":
    # Example run — needs a real MAP_KEY in the environment to actually hit the API.
    result = fetch_firms_data(
        source="VIIRS_SNPP_NRT",
        day_range=1,
        area_coords="-125,32,-114,42",  # rough California bounding box
    )
    print(result.head())
    print(f"\n{len(result)} detections fetched.")
