"""Which flagged sites a camera can actually see, and where the gaps are.

The gap analysis is the part that works on day one. With an empty registry
every high-risk detection is uncovered, and the useful output is not "no
cameras" but "one camera here would cover 37 of them". That is a greedy
set-cover over the uncovered events: repeatedly take the position that covers
the most still-uncovered events, which is the standard approximation and good
enough to rank siting candidates.

Nothing here invents a feed. A site with no camera is reported as having no
camera.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

import config
from src.cameras.registry import DEFAULT_COVERAGE_KM, haversine_km

# Cameras are for verifying things worth a response, so the gap analysis looks
# at the tiers that would actually be dispatched on.
COVERED_TIERS = ("HIGH", "CRITICAL")


def _event_rows(events: pd.DataFrame, tiers: tuple[str, ...] = COVERED_TIERS) -> pd.DataFrame:
    if events is None or events.empty:
        return pd.DataFrame(columns=["event_id", "latitude", "longitude", "risk_score", "risk_level"])
    rows = events[events["risk_level"].isin(tiers)] if "risk_level" in events.columns else events
    keep = [c for c in ("event_id", "grid_cell", "latitude", "longitude", "risk_score", "risk_level",
                        "state", "district", "place_name", "category", "facility") if c in rows.columns]
    return rows[keep].copy()


def _distance_matrix(events: pd.DataFrame, cameras: list[dict[str, Any]]) -> np.ndarray:
    """Kilometres from every event to every camera. Vectorised haversine: the
    per-pair helper is fine for a handful of lookups but not for 400 x N."""
    if events.empty or not cameras:
        return np.empty((len(events), len(cameras)))
    rad = np.pi / 180
    elat = events["latitude"].to_numpy(dtype=float)[:, None] * rad
    elon = events["longitude"].to_numpy(dtype=float)[:, None] * rad
    clat = np.array([float(c["latitude"]) for c in cameras])[None, :] * rad
    clon = np.array([float(c["longitude"]) for c in cameras])[None, :] * rad
    dlat, dlon = clat - elat, clon - elon
    h = np.sin(dlat / 2) ** 2 + np.cos(elat) * np.cos(clat) * np.sin(dlon / 2) ** 2
    return 2 * 6371.0088 * np.arcsin(np.minimum(1.0, np.sqrt(h)))


def match_events(events: pd.DataFrame, cameras: list[dict[str, Any]],
                 tiers: tuple[str, ...] = COVERED_TIERS) -> dict[str, Any]:
    """Split the flagged events into those a registered camera can see and
    those nobody is watching."""
    rows = _event_rows(events, tiers)
    if rows.empty or not cameras:
        return {
            "events": rows,
            "covered": rows.iloc[0:0],
            "uncovered": rows,
            "by_camera": {c["id"]: rows.iloc[0:0] for c in cameras},
            "nearest_km": {},
        }

    dist = _distance_matrix(rows, cameras)
    radius = np.array([float(c.get("coverage_km", DEFAULT_COVERAGE_KM)) for c in cameras])[None, :]
    within = dist <= radius

    covered_mask = within.any(axis=1)
    nearest_idx = dist.argmin(axis=1)
    nearest_km = {
        str(rows.iloc[i].get("event_id")): (cameras[int(nearest_idx[i])], float(dist[i, nearest_idx[i]]))
        for i in range(len(rows))
    }

    by_camera: dict[str, pd.DataFrame] = {}
    for j, camera in enumerate(cameras):
        seen = rows[within[:, j]]
        by_camera[camera["id"]] = seen.assign(distance_km=np.round(dist[within[:, j], j], 2))

    return {
        "events": rows,
        "covered": rows[covered_mask],
        "uncovered": rows[~covered_mask],
        "by_camera": by_camera,
        "nearest_km": nearest_km,
    }


def siting_candidates(uncovered: pd.DataFrame, radius_km: float = DEFAULT_COVERAGE_KM,
                      limit: int = 8) -> list[dict[str, Any]]:
    """Where a camera would do the most good, best first.

    Greedy set cover: take the uncovered event whose radius contains the most
    other uncovered events, claim them, repeat. Candidate positions are the
    events themselves, which keeps every suggestion a place something was
    actually detected rather than an arbitrary grid point.
    """
    if uncovered is None or uncovered.empty:
        return []

    rows = uncovered.reset_index(drop=True)
    dist = _distance_matrix(rows, [
        {"latitude": r.latitude, "longitude": r.longitude} for r in rows.itertuples()
    ])
    within = dist <= radius_km

    remaining = np.ones(len(rows), dtype=bool)
    out: list[dict[str, Any]] = []
    for _ in range(limit):
        if not remaining.any():
            break
        gains = (within & remaining[:, None]).sum(axis=0)
        gains[~remaining] = 0  # only site a camera where something is still unwatched
        best = int(gains.argmax())
        claimed_mask = within[:, best] & remaining
        if not claimed_mask.any():
            break
        claimed = rows[claimed_mask]
        anchor = claimed.loc[claimed["risk_score"].idxmax()] if "risk_score" in claimed else claimed.iloc[0]
        out.append({
            "latitude": round(float(rows.at[best, "latitude"]), 4),
            "longitude": round(float(rows.at[best, "longitude"]), 4),
            "events_covered": int(claimed_mask.sum()),
            "max_risk": float(claimed["risk_score"].max()) if "risk_score" in claimed else 0.0,
            "state": anchor.get("state") if hasattr(anchor, "get") else None,
            "district": anchor.get("district") if hasattr(anchor, "get") else None,
            "place": anchor.get("place_name") if hasattr(anchor, "get") else None,
            "top_event": anchor.get("event_id") if hasattr(anchor, "get") else None,
            "facility": anchor.get("facility") if hasattr(anchor, "get") else None,
        })
        remaining &= ~claimed_mask
    return out


def summary(events: pd.DataFrame, cameras: list[dict[str, Any]],
            tiers: tuple[str, ...] = COVERED_TIERS) -> dict[str, Any]:
    """Headline coverage numbers plus the ranked siting suggestions."""
    match = match_events(events, cameras, tiers)
    rows, covered, uncovered = match["events"], match["covered"], match["uncovered"]
    radius = (
        float(np.median([float(c.get("coverage_km", DEFAULT_COVERAGE_KM)) for c in cameras]))
        if cameras else DEFAULT_COVERAGE_KM
    )
    critical_uncovered = (
        int((uncovered["risk_level"] == "CRITICAL").sum())
        if not uncovered.empty and "risk_level" in uncovered.columns else 0
    )
    return {
        **match,
        "n_cameras": len(cameras),
        "n_flagged": len(rows),
        "n_covered": len(covered),
        "n_uncovered": len(uncovered),
        "n_critical_uncovered": critical_uncovered,
        "coverage_share": (len(covered) / len(rows)) if len(rows) else 0.0,
        "candidates": siting_candidates(uncovered, radius_km=radius),
        "radius_km": radius,
        "tiers": tiers,
    }


def nearest_camera(lat: float, lon: float, cameras: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, float]:
    """The closest camera to a point, and how far it is. Used to answer the
    single most common question about one event: is anyone watching this?"""
    if not cameras:
        return None, float("inf")
    best, best_km = None, float("inf")
    for camera in cameras:
        km = haversine_km(lat, lon, float(camera["latitude"]), float(camera["longitude"]))
        if km < best_km:
            best, best_km = camera, km
    return best, best_km


def covers(camera: dict[str, Any], lat: float, lon: float) -> bool:
    km = haversine_km(lat, lon, float(camera["latitude"]), float(camera["longitude"]))
    return km <= float(camera.get("coverage_km", DEFAULT_COVERAGE_KM))


__all__ = [
    "COVERED_TIERS", "match_events", "siting_candidates", "summary", "nearest_camera", "covers",
    "config",
]
