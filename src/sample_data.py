"""Synthetic demo data so the app runs end-to-end before a FIRMS key / live
OSM pull is available. Mirrors real FIRMS column names so the rest of the
pipeline can't tell the difference. Used automatically as a fallback by
pipeline.py, and mirrors the roadmap's own fallback plan ("cache a dataset
locally beforehand, demo on that").
"""
from __future__ import annotations

import datetime as dt

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

import config

RNG = np.random.default_rng(42)

# name, lat, lon, kind ("industrial_persistent" | "nonindustrial_persistent"
# | "industrial_transient"), days_active, frp_range, confidence
CLUSTERS = [
    ("Tata Steel, Jamshedpur", 22.8046, 86.1850, "industrial_persistent", 26, (30, 65), "h"),
    ("Rourkela Steel Plant", 22.2200, 84.8600, "industrial_persistent", 24, (28, 58), "h"),
    ("Jharia Coalfield (seam fire)", 23.7500, 86.4100, "nonindustrial_persistent", 21, (8, 20), "n"),
    ("Noamundi Iron Mine", 22.1550, 85.5300, "industrial_transient", 8, (12, 30), "n"),
    ("Barbil Mining Cluster", 22.1000, 85.3800, "industrial_transient", 6, (10, 22), "n"),
]

# small square "industrial zone" footprints used by the OSM fallback
INDUSTRIAL_ZONES = [
    ("Tata Steel, Jamshedpur", 22.8046, 86.1850),
    ("Rourkela Steel Plant", 22.2200, 84.8600),
    ("Noamundi Iron Mine", 22.1550, 85.5300),
    ("Barbil Mining Cluster", 22.1000, 85.3800),
]


def generate_sample_hotspots(window_days: int = config.PERSISTENCE_WINDOW_DAYS) -> pd.DataFrame:
    today = dt.date.today()
    rows = []

    for name, lat, lon, kind, days_active, frp_range, base_conf in CLUSTERS:
        active_days = RNG.choice(range(window_days), size=days_active, replace=False)
        for offset in active_days:
            acq_date = today - dt.timedelta(days=int(offset))
            jitter_lat = RNG.normal(0, 0.003)
            jitter_lon = RNG.normal(0, 0.003)
            frp = float(RNG.uniform(*frp_range))
            rows.append(
                {
                    "latitude": lat + jitter_lat,
                    "longitude": lon + jitter_lon,
                    "brightness": float(RNG.uniform(320, 400)),
                    "scan": 0.4,
                    "track": 0.4,
                    "acq_date": pd.Timestamp(acq_date),
                    "acq_time": int(RNG.choice([130, 145, 1830, 1845])),
                    "satellite": "N",
                    "instrument": "VIIRS",
                    "confidence": base_conf,
                    "version": "2.0NRT",
                    "bright_t31": float(RNG.uniform(290, 320)),
                    "frp": frp,
                    "daynight": RNG.choice(["D", "N"]),
                    "source": "SAMPLE_DATA",
                    "cluster_name": name,
                }
            )

    # scattered one-off farmland / noise points across the bounding box
    n_scatter = 60
    for _ in range(n_scatter):
        lat = RNG.uniform(config.BBOX["min_lat"], config.BBOX["max_lat"])
        lon = RNG.uniform(config.BBOX["min_lon"], config.BBOX["max_lon"])
        offset = RNG.integers(0, window_days)
        acq_date = today - dt.timedelta(days=int(offset))
        rows.append(
            {
                "latitude": lat,
                "longitude": lon,
                "brightness": float(RNG.uniform(300, 330)),
                "scan": 0.5,
                "track": 0.5,
                "acq_date": pd.Timestamp(acq_date),
                "acq_time": int(RNG.choice([130, 145, 1830, 1845])),
                "satellite": "N",
                "instrument": "VIIRS",
                "confidence": "l",
                "version": "2.0NRT",
                "bright_t31": float(RNG.uniform(285, 305)),
                "frp": float(RNG.uniform(1, 6)),
                "daynight": RNG.choice(["D", "N"]),
                "source": "SAMPLE_DATA",
                "cluster_name": "scattered",
            }
        )

    df = pd.DataFrame(rows)
    return df.reset_index(drop=True)


def generate_sample_industrial_zones() -> gpd.GeoDataFrame:
    """Small square polygons standing in for real OSM landuse=industrial areas."""
    half_deg = 0.02
    geoms = []
    names = []
    for name, lat, lon in INDUSTRIAL_ZONES:
        geoms.append(box(lon - half_deg, lat - half_deg, lon + half_deg, lat + half_deg))
        names.append(name)
    return gpd.GeoDataFrame({"name": names, "landuse": "industrial"}, geometry=geoms, crs="EPSG:4326")
