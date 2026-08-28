"""DEMO DATA — synthetic, clearly labeled as such everywhere it surfaces in
the UI. Mirrors real FIRMS column names so the rest of the pipeline can't
tell the difference, and is written once to config.DEMO_DATASET_PATH so
Demo Mode is a genuinely fixed, reproducible dataset (not regenerated with
drifting random jitter on every dashboard interaction within a session).

FRP ranges here are calibrated against the real percentiles this project
observed from live FIRMS data for this region (p50=1.7MW, p90=5.2MW,
p99=10.5MW, max=19.4MW) — see config.py — so demo numbers don't contradict
what real data actually looks like.
"""
from __future__ import annotations

import datetime as dt

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

import config

RNG = np.random.default_rng(42)

# name, lat, lon, days_active, frp_range, confidence — tuned so each of the
# 8 classification categories is reachable from the demo dataset alone.
CLUSTERS = [
    ("Tata Steel, Jamshedpur", 22.8046, 86.1850, 24, (8.0, 18.0), "h"),      # -> Likely Industrial Fire
    ("Rourkela Steel Plant", 22.2200, 84.8600, 22, (8.0, 16.0), "h"),        # -> Likely Industrial Fire
    ("Jharia Coalfield (seam fire)", 23.7500, 86.4100, 21, (1.0, 4.0), "n"), # -> Persistent Industrial Activity (low FRP, tagged industrial via OSM quarry)
    ("Noamundi Iron Mine", 22.1550, 85.5300, 4, (3.5, 8.5), "n"),            # -> Transient Industrial Flare
    ("Barbil Mining Cluster", 22.1000, 85.3800, 3, (3.0, 7.0), "n"),         # -> Transient Industrial Flare
]

INDUSTRIAL_ZONES = [
    ("Tata Steel, Jamshedpur", 22.8046, 86.1850),
    ("Rourkela Steel Plant", 22.2200, 84.8600),
    ("Noamundi Iron Mine", 22.1550, 85.5300),
    ("Barbil Mining Cluster", 22.1000, 85.3800),
]


def _generate(window_days: int = config.PERSISTENCE_DEFAULT_WINDOW_DAYS) -> pd.DataFrame:
    today = dt.date.today()
    rows = []

    for name, lat, lon, days_active, frp_range, base_conf in CLUSTERS:
        active_days = RNG.choice(range(window_days), size=min(days_active, window_days), replace=False)
        for offset in active_days:
            acq_date = today - dt.timedelta(days=int(offset))
            rows.append({
                "latitude": lat + RNG.normal(0, 0.003), "longitude": lon + RNG.normal(0, 0.003),
                "brightness": float(RNG.uniform(320, 400)), "scan": 0.4, "track": 0.4,
                "acq_date": pd.Timestamp(acq_date), "acq_time": int(RNG.choice([130, 145, 1830, 1845])),
                "satellite": "N", "instrument": "VIIRS", "confidence": base_conf, "version": "2.0NRT",
                "bright_t31": float(RNG.uniform(290, 320)), "frp": float(RNG.uniform(*frp_range)),
                "daynight": RNG.choice(["D", "N"]), "source": "DEMO_DATA", "cluster_name": name,
            })

    # "Likely Agricultural Burning" requires BOTH a recent date (inside the
    # pipeline's rolling window, or it gets filtered out before scoring) AND
    # a burn-season month — so it only appears in the demo when at least one
    # of the last FIRMS_TOTAL_DAYS actually falls in a burn month. Outside
    # that window (e.g. running the demo in monsoon season), this category
    # genuinely won't appear — matching what the real live data showed too,
    # rather than faking a date that would just get filtered out anyway.
    burn_season_recent_days = [
        today - dt.timedelta(days=d) for d in range(config.FIRMS_TOTAL_DAYS)
        if (today - dt.timedelta(days=d)).month in config.AGRI_BURN_MONTHS
    ]
    for _ in range(18 if burn_season_recent_days else 0):
        lat = RNG.uniform(config.BBOX["min_lat"], config.BBOX["max_lat"])
        lon = RNG.uniform(config.BBOX["min_lon"], config.BBOX["max_lon"])
        acq_date = burn_season_recent_days[RNG.integers(0, len(burn_season_recent_days))]
        rows.append({
            "latitude": lat, "longitude": lon, "brightness": float(RNG.uniform(300, 330)),
            "scan": 0.5, "track": 0.5, "acq_date": pd.Timestamp(acq_date),
            "acq_time": int(RNG.choice([130, 145, 1830, 1845])), "satellite": "N", "instrument": "VIIRS",
            "confidence": RNG.choice(["l", "n"]), "version": "2.0NRT", "bright_t31": float(RNG.uniform(290, 310)),
            "frp": float(RNG.uniform(1, 5)), "daynight": RNG.choice(["D", "N"]), "source": "DEMO_DATA",
            "cluster_name": "agri_burning_demo",
        })

    # A forced off-season, moderate/high-confidence, non-industrial, one-off
    # batch so "Likely Wildfire" is reachable too.
    for _ in range(10):
        lat = RNG.uniform(config.BBOX["min_lat"], config.BBOX["max_lat"])
        lon = RNG.uniform(config.BBOX["min_lon"], config.BBOX["max_lon"])
        acq_date = dt.date(today.year, RNG.choice([6, 7, 8]), int(RNG.integers(1, 28)))
        rows.append({
            "latitude": lat, "longitude": lon, "brightness": float(RNG.uniform(320, 360)),
            "scan": 0.5, "track": 0.5, "acq_date": pd.Timestamp(acq_date),
            "acq_time": int(RNG.choice([130, 145, 1830, 1845])), "satellite": "N", "instrument": "VIIRS",
            "confidence": "h", "version": "2.0NRT", "bright_t31": float(RNG.uniform(300, 320)),
            "frp": float(RNG.uniform(2, 6)), "daynight": RNG.choice(["D", "N"]), "source": "DEMO_DATA",
            "cluster_name": "wildfire_demo",
        })

    # scattered one-off low-confidence points -> Sun Glint / False Positive
    for _ in range(50):
        lat = RNG.uniform(config.BBOX["min_lat"], config.BBOX["max_lat"])
        lon = RNG.uniform(config.BBOX["min_lon"], config.BBOX["max_lon"])
        offset = RNG.integers(0, window_days)
        acq_date = today - dt.timedelta(days=int(offset))
        rows.append({
            "latitude": lat, "longitude": lon, "brightness": float(RNG.uniform(300, 330)),
            "scan": 0.5, "track": 0.5, "acq_date": pd.Timestamp(acq_date),
            "acq_time": int(RNG.choice([130, 145, 1830, 1845])), "satellite": "N", "instrument": "VIIRS",
            "confidence": "l", "version": "2.0NRT", "bright_t31": float(RNG.uniform(285, 305)),
            "frp": float(RNG.uniform(0.2, 3)), "daynight": RNG.choice(["D", "N"]), "source": "DEMO_DATA",
            "cluster_name": "scattered",
        })

    return pd.DataFrame(rows).reset_index(drop=True)


def generate_sample_hotspots(window_days: int = config.PERSISTENCE_DEFAULT_WINDOW_DAYS, force_regenerate: bool = False) -> pd.DataFrame:
    """Load the fixed demo dataset from disk, generating it once if it
    doesn't exist yet (or if force_regenerate=True)."""
    if config.DEMO_DATASET_PATH.exists() and not force_regenerate:
        df = pd.read_csv(config.DEMO_DATASET_PATH)
        df["acq_date"] = pd.to_datetime(df["acq_date"])
        return df

    df = _generate(window_days)
    df.to_csv(config.DEMO_DATASET_PATH, index=False)
    return df


def generate_sample_industrial_zones() -> gpd.GeoDataFrame:
    """Small square polygons standing in for real OSM landuse=industrial areas."""
    half_deg = 0.02
    geoms = [box(lon - half_deg, lat - half_deg, lon + half_deg, lat + half_deg) for _, lat, lon in INDUSTRIAL_ZONES]
    names = [name for name, _, _ in INDUSTRIAL_ZONES]
    return gpd.GeoDataFrame({"name": names, "landuse": "industrial"}, geometry=geoms, crs="EPSG:4326")


# --- National (India-wide) demo data -----------------------------------------
# Real approximate locations of known industrial/mining/thermal-power belts
# across several states, so the national demo view has a plausible spatial
# spread rather than uniform noise — but the values (FRP, confidence, which
# days) are synthetic. A separate, independently-seeded RNG so this never
# interacts with the regional demo generator's state.
_NATIONAL_RNG = np.random.default_rng(4242)

NATIONAL_CLUSTERS = [
    ("Jharia/Dhanbad, Jharkhand", 23.7500, 86.4100),
    ("Bokaro Steel, Jharkhand", 23.6700, 86.1500),
    ("Jamshedpur (Tata Steel), Jharkhand", 22.8000, 86.1800),
    ("Ranchi Industrial Area, Jharkhand", 23.3400, 85.3100),
    ("Noamundi Mines, Jharkhand", 22.1600, 85.5300),
    ("Talcher Coalfield, Odisha", 20.9500, 85.2300),
    ("Angul Industrial Belt, Odisha", 20.8400, 85.1000),
    ("Rourkela Steel Plant, Odisha", 22.2200, 84.8600),
    ("Paradip Refinery, Odisha", 20.3200, 86.6100),
    ("Sundargarh, Odisha", 22.1200, 84.0300),
    ("Keonjhar Mining Belt, Odisha", 21.6300, 85.5800),
    ("Joda-Barbil Mines, Odisha", 22.0500, 85.3300),
    ("Korba Coalfield, Chhattisgarh", 22.3500, 82.6800),
    ("Raipur Steel Belt, Chhattisgarh", 21.2500, 81.6300),
    ("Bhilai Steel Plant, Chhattisgarh", 21.2100, 81.4300),
    ("Durg Industrial, Chhattisgarh", 21.1900, 81.2800),
    ("Chandrapur Thermal Belt, Maharashtra", 19.9500, 79.3000),
    ("Nagpur Industrial, Maharashtra", 21.1500, 79.0900),
    ("Mumbai-Trombay Refinery, Maharashtra", 19.0000, 72.9000),
    ("Singrauli Coal Belt, Madhya Pradesh", 24.2000, 82.6800),
    ("Bhopal Industrial, Madhya Pradesh", 23.2600, 77.4100),
    ("Bina Refinery, Madhya Pradesh", 24.1900, 78.2000),
    ("Asansol-Durgapur, West Bengal", 23.6800, 87.2900),
    ("Haldia Petrochemical, West Bengal", 22.0300, 88.1100),
    ("Singareni Coalfields, Telangana", 18.4400, 79.5000),
    ("Vizag Steel Plant, Andhra Pradesh", 17.6200, 83.1000),
    ("Vijayawada Industrial, Andhra Pradesh", 16.5000, 80.6300),
    ("Rajahmundry Industrial, Andhra Pradesh", 17.0000, 81.7800),
    ("Jamnagar Refinery, Gujarat", 22.2400, 69.8300),
    ("Vadodara Petrochemical, Gujarat", 22.3000, 73.1900),
    ("Hazira Industrial, Gujarat", 21.1200, 72.6500),
    ("Bhavnagar Industrial, Gujarat", 21.7600, 72.1500),
    ("Bathinda Thermal, Punjab", 30.2100, 74.9500),
    ("Panipat Refinery, Haryana", 29.3900, 76.9800),
    ("Faridabad Industrial, Haryana", 28.4100, 77.3100),
    ("Neyveli Lignite, Tamil Nadu", 11.6100, 79.4800),
    ("Chennai-Manali Refinery, Tamil Nadu", 13.1700, 80.2700),
    ("Salem Steel, Tamil Nadu", 11.6600, 78.1500),
    ("Tuticorin Industrial, Tamil Nadu", 8.7600, 78.1300),
    ("Bellary Steel Belt, Karnataka", 15.1400, 76.9200),
    ("Mangalore Refinery, Karnataka", 12.9200, 74.8300),
    ("Kochi Refinery, Kerala", 9.9700, 76.2800),
    ("Barmer Refinery, Rajasthan", 25.7500, 71.3800),
    ("Kota Industrial, Rajasthan", 25.2100, 75.8600),
    ("Guwahati Refinery, Assam", 26.1800, 91.7500),
    ("Digboi Refinery, Assam", 27.3800, 95.6200),
    ("Numaligarh Refinery, Assam", 26.5500, 93.7200),
    ("Barauni Refinery, Bihar", 25.4700, 85.9800),
    ("Muzaffarpur Thermal, Bihar", 26.1200, 85.3600),
]


def generate_national_demo_hotspots(day_range: int | None = None) -> pd.DataFrame:
    """Synthetic India-wide detections spanning ~50 real major industrial/
    mining/refinery/thermal-power locations across 15 states, over the
    national pipeline's short (latest 24-48h) window.

    Volume is deliberately high (order of thousands, not hundreds) — a real
    India-wide FIRMS pull over 24-48h routinely returns this many detections
    (especially during agricultural burn season), and Demo Mode's whole
    purpose is to look and behave like a real run regardless of what live
    data happens to be available at demo time. Each real location gets a
    cluster of nearby detections (a real industrial complex spans many
    adjacent VIIRS pixels, not one point), plus nationwide scattered
    low-confidence noise representing background agricultural/small-fire
    activity."""
    import config as _config

    day_range = day_range or _config.NATIONAL_DAY_RANGE
    today = dt.date.today()
    rows = []

    for name, lat, lon in NATIONAL_CLUSTERS:
        n_obs = int(_NATIONAL_RNG.integers(15, 60))
        for _ in range(n_obs):
            offset = int(_NATIONAL_RNG.integers(0, day_range + 1))
            acq_date = today - dt.timedelta(days=offset)
            rows.append({
                "latitude": lat + _NATIONAL_RNG.normal(0, 0.06), "longitude": lon + _NATIONAL_RNG.normal(0, 0.06),
                "brightness": float(_NATIONAL_RNG.uniform(310, 380)), "scan": 0.4, "track": 0.4,
                "acq_date": pd.Timestamp(acq_date), "acq_time": int(_NATIONAL_RNG.choice([130, 145, 1830, 1845])),
                "satellite": _NATIONAL_RNG.choice(["N20", "N21"]), "instrument": "VIIRS",
                "confidence": _NATIONAL_RNG.choice(["n", "h"]), "version": "2.0NRT",
                "bright_t31": float(_NATIONAL_RNG.uniform(290, 315)), "frp": float(_NATIONAL_RNG.uniform(2, 15)),
                "daynight": _NATIONAL_RNG.choice(["D", "N"]), "source": "DEMO_DATA", "cluster_name": name,
            })

    # scattered nationwide noise (background agricultural burning, small
    # non-industrial fires, occasional sun glint) — real India-wide FIRMS
    # pulls are dominated by this, not just industrial-belt detections.
    india_bbox = {"min_lat": 8.0, "max_lat": 35.0, "min_lon": 68.0, "max_lon": 97.0}
    for _ in range(900):
        lat = _NATIONAL_RNG.uniform(india_bbox["min_lat"], india_bbox["max_lat"])
        lon = _NATIONAL_RNG.uniform(india_bbox["min_lon"], india_bbox["max_lon"])
        offset = int(_NATIONAL_RNG.integers(0, day_range + 1))
        acq_date = today - dt.timedelta(days=offset)
        rows.append({
            "latitude": lat, "longitude": lon, "brightness": float(_NATIONAL_RNG.uniform(300, 330)),
            "scan": 0.5, "track": 0.5, "acq_date": pd.Timestamp(acq_date),
            "acq_time": int(_NATIONAL_RNG.choice([130, 145, 1830, 1845])),
            "satellite": _NATIONAL_RNG.choice(["N20", "N21"]), "instrument": "VIIRS",
            "confidence": "l", "version": "2.0NRT", "bright_t31": float(_NATIONAL_RNG.uniform(285, 305)),
            "frp": float(_NATIONAL_RNG.uniform(0.5, 4)), "daynight": _NATIONAL_RNG.choice(["D", "N"]),
            "source": "DEMO_DATA", "cluster_name": "scattered_national",
        })

    return pd.DataFrame(rows).reset_index(drop=True)
