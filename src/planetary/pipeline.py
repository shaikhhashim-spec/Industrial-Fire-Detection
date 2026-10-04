"""Rolling global thermal observations, with bounded offline context and weather."""
from __future__ import annotations

import hashlib
import math
import time
from collections import defaultdict
from collections.abc import Callable

import numpy as np
import pandas as pd

import config
from src.firms.fetch import fetch_global_hotspots
from src.geospatial.grid import assign_grid_cell
from src.ml.rules import normalize_confidence
from src.planetary.context import enrich_context, facilities_geojson, load_references
from src.processing.cleaning import clean_hotspots
from src.utils import wind
from src.utils.spread import calculate_spread_potential

SATELLITES = {"VIIRS_SNPP_NRT": "VIIRS S-NPP", "VIIRS_NOAA20_NRT": "VIIRS NOAA-20", "VIIRS_NOAA21_NRT": "VIIRS NOAA-21"}


def _level(score: int) -> str:
    return "CRITICAL" if score >= 76 else "HIGH" if score >= 51 else "MODERATE" if score >= 26 else "LOW"


def _finite(value) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _region(lat: float, lon: float) -> str:
    for key, region in config.GLOBAL_REGIONS.items():
        if key in ("global", "india"):
            continue
        b = region["bbox"]
        if b["min_lat"] <= lat <= b["max_lat"] and b["min_lon"] <= lon <= b["max_lon"]:
            return region["name"]
    return "Global"


def _select_events(events: list[dict], limit: int) -> list[dict]:
    """Keep one priority event per occupied degree tile before filling by rank."""
    if limit < 1:
        raise ValueError("Global event limit must be positive")
    ranked = sorted(events, key=lambda e: (-e["riskScore"], -e["frp"], e["id"]))
    if len(ranked) <= limit:
        return ranked
    tiles, chosen = set(), []
    for event in ranked:
        tile = (math.floor(event["latitude"]), math.floor(event["longitude"]))
        if tile not in tiles:
            chosen.append(event)
            tiles.add(tile)
    # If even occupied tiles exceed the budget, sampling cannot cover them all.
    selected = chosen[:limit]
    ids = {e["id"] for e in selected}
    for event in ranked:
        if len(selected) >= limit:
            break
        if event["id"] not in ids:
            selected.append(event)
    return sorted(selected, key=lambda e: (-e["riskScore"], -e["frp"], e["id"]))


def enrich_weather(events: list[dict], provider: Callable | None = None, limit: int | None = None) -> dict:
    """Consume Boyle's weather API without changing wind.py.

    Provider accepts (lat, lon) and returns speed_kmh, direction_deg, source,
    observed_at, humidity_pct, temperature_c and precipitation_mm.
    Legacy get_wind remains supported; missing weather never becomes a score.
    """
    provider = provider or getattr(wind, "get_weather", wind.get_wind)
    limit = config.GLOBAL_WEATHER_MAX_EVENTS if limit is None else max(0, limit)
    candidates = sorted((e for e in events if e["frp"] >= config.GLOBAL_PLUME_FRP_MIN_MW), key=lambda e: -e["frp"])
    enriched, plumes, spread = 0, 0, 0
    started, attempted = time.monotonic(), 0
    deadline_exceeded = False
    for event in candidates[:limit]:
        if time.monotonic() - started >= config.GLOBAL_WEATHER_BUDGET_SECONDS:
            deadline_exceeded = True
            break
        attempted += 1
        try:
            weather = provider(event["latitude"], event["longitude"])
            speed, direction = _finite(weather.get("speed_kmh")), _finite(weather.get("direction_deg"))
            source = weather.get("source", "unknown")
            # Defaults are not observed weather and must not drive a live-looking cone.
            if speed is None or direction is None or speed < 0 or not 0 <= direction <= 360 or source not in ("open-meteo", "cache", "stale_cache"):
                continue
            enriched += 1
            event["plume"] = {
                "windSpeedKmh": round(speed, 1), "windDirectionDeg": round(direction % 360, 1),
                "downwindBearingDeg": round(wind.downwind_bearing(direction), 1),
                "coneLengthKm": round(wind.dispersion_cone_length_km(speed, event["frp"]), 1),
                "polygon": [[(lon + 180) % 360 - 180, lat] for lat, lon in wind.dispersion_cone_polygon(
                    event["latitude"], event["longitude"], direction, speed, event["frp"])],
                "source": source, "observedAt": weather.get("observed_at", weather.get("observedAt")),
                "estimated": True,
            }
            plumes += 1
            normalized = {**weather, "speed_kmh": speed, "source": source,
                          "humidity_pct": weather.get("humidity_pct", weather.get("relative_humidity_2m")),
                          "temperature_c": weather.get("temperature_c", weather.get("temperature_2m")),
                          "precipitation_mm": weather.get("precipitation_mm", weather.get("precipitation"))}
            potential = calculate_spread_potential(normalized, event["frp"])
            if potential is not None:
                event["spreadPotential"] = potential
                spread += 1
        except (ValueError, TypeError, KeyError, RuntimeError, OSError):
            continue
    return {"weatherEnrichedEvents": enriched, "plumeEvents": plumes, "spreadScoredEvents": spread,
            "weatherEligibleEvents": len(candidates), "weatherBudget": limit,
            "weatherAttemptedEvents": attempted, "weatherBudgetSeconds": config.GLOBAL_WEATHER_BUDGET_SECONDS,
            "weatherDeadlineExceeded": deadline_exceeded,
            "weatherScope": "Highest-FRP exported events only; defaults are excluded, stale wind is labeled"}


def build_global_payload(raw: pd.DataFrame, *, max_events: int | None = None,
                         weather_provider: Callable | None = None, weather_limit: int | None = None) -> dict:
    attrs = dict(raw.attrs)
    # Validate before the existing cleaner converts HHMM to integers, so infinity
    # or fractional values cannot crash a complete otherwise valid sensor batch.
    valid_raw = raw.copy()
    if not raw.empty:
        original_frp = pd.to_numeric(raw["frp"], errors="coerce")
        times = pd.to_numeric(raw["acq_time"], errors="coerce")
        valid = (np.isfinite(original_frp) & (original_frp >= 0) & np.isfinite(times)
                 & times.between(0, 2359) & (times % 100 < 60) & (times % 1 == 0))
        valid_raw = raw[valid].copy()
        if "frpObserved" not in valid_raw:
            # This boundary validates raw FIRMS values before any fill/clip.
            valid_raw["frpObserved"] = True
        valid_raw["acq_time"] = times[valid]
        valid_raw["acq_date"] = pd.to_datetime(valid_raw.acq_date, errors="coerce", utc=True).dt.tz_localize(None)
        # Public CSVs spell out VIIRS confidence; the area API uses l/n/h.
        valid_raw["confidence"] = valid_raw.confidence.astype(str).str.strip().str.lower().replace(
            {"low": "l", "nominal": "n", "high": "h"})
        if "source" not in valid_raw or not valid_raw.source.isin(SATELLITES).all():
            raise ValueError("Global observations require a supported sensor source")
    clean, report = clean_hotspots(valid_raw, bbox={})
    if not clean.empty:
        dates = clean.acq_date.dt.tz_localize("UTC")
        clean["acquired_at"] = dates + pd.to_timedelta(clean.acq_time // 100, unit="h") + pd.to_timedelta(clean.acq_time % 100, unit="m")
        now = pd.Timestamp.now(tz="UTC")
        hours = attrs.get("window_hours", config.GLOBAL_FIRMS_WINDOW_HOURS)
        clean = clean[clean.acquired_at.between(now - pd.Timedelta(hours=hours), now + pd.Timedelta(minutes=15))]
    if clean.empty and not raw.empty:
        raise RuntimeError("No valid observations within the requested rolling window; previous export preserved")
    clean = assign_grid_cell(normalize_confidence(clean)) if not clean.empty else clean
    events = []
    all_count, total_frp = 0, 0.0
    if not clean.empty:
        clean["confidence_numeric"] = clean.confidence_numeric.clip(0, 100)
        clean["night"] = clean.get("daynight", pd.Series("D", index=clean.index)).eq("N")
        clean["low_confidence"] = clean.confidence_numeric < 50
        satellite_columns = {}
        for index, source in enumerate(SATELLITES):
            column = f"sensor_{index}"
            clean[column] = clean.source.eq(source)
            satellite_columns[column] = SATELLITES[source]
        grouped = clean.groupby("grid_cell", sort=True)
        summary = grouped.agg(
            detections=("frp", "size"), frp=("frp", "max"), mean_frp=("frp", "mean"),
            confidence=("confidence_numeric", "mean"), days=("acq_date", "nunique"),
            first_seen=("acq_date", "min"), last_seen=("acq_date", "max"),
            night_passes=("night", "sum"), low_share=("low_confidence", "mean"),
            **{column: (column, "max") for column in satellite_columns},
        )
        peak = clean.loc[grouped.frp.idxmax()].set_index("grid_cell")
        latest = clean.loc[grouped.acquired_at.idxmax()].set_index("grid_cell")
        summary["latitude"], summary["longitude"] = peak.latitude, peak.longitude
        summary["brightness"] = peak.get("bright_ti4", peak.get("brightness", pd.Series(index=peak.index, dtype=float)))
        summary["satellite"] = latest.source.map(SATELLITES)
        summary["daynight"] = latest.get("daynight", "D")
        summary["first_seen"] = summary.first_seen.dt.strftime("%Y-%m-%d")
        summary["last_seen"] = summary.last_seen.dt.strftime("%Y-%m-%d")
        summary["score"] = (70 * (summary.frp / 100).clip(upper=1) + 30 * summary.confidence / 100).round().astype(int)
        summary["id"] = ["GL-" + hashlib.sha256(str(cell).encode()).hexdigest()[:16].upper() for cell in summary.index]
        all_count, total_frp = len(summary), float(summary.frp.round(2).sum())
        # Select inexpensive summaries before building evidence/history JSON.
        lightweight = [{"id": r.id, "latitude": r.latitude, "longitude": r.longitude,
                        "riskScore": r.score, "frp": r.frp} for r in summary.itertuples()]
        selected = _select_events(lightweight, config.GLOBAL_MAX_EVENTS if max_events is None else max_events)
        selected_ids = {event["id"] for event in selected}
        summary = summary[summary.id.isin(selected_ids)]
        selected_clean = clean[clean.grid_cell.isin(summary.index)]
        selected_clean = selected_clean.assign(
            history_satellite=selected_clean.source.map(SATELLITES),
            history_pass=selected_clean.get("daynight", pd.Series(None, index=selected_clean.index, dtype=object)))
        daily = selected_clean.groupby(["grid_cell", "acq_date", "history_satellite", "history_pass"], dropna=False).agg(
            frp=("frp", "max"), confidence=("confidence_numeric", "mean"),
            frpObserved=("frpObserved", "all")).reset_index()
        daily["date"] = daily.acq_date.dt.strftime("%Y-%m-%d")
        history_by_cell = defaultdict(list)
        for day in daily.itertuples():
            history_by_cell[day.grid_cell].append({
                "date": day.date, "frp": round(day.frp, 1) if day.frpObserved else None,
                "frpObserved": bool(day.frpObserved), "confidence": round(day.confidence, 1),
                "satellite": day.history_satellite, "instrument": "VIIRS",
                "daynight": day.history_pass if pd.notna(day.history_pass) else None,
            })
        for row in summary.reset_index().to_dict(orient="records"):
            cell, frp, confidence, days = row["grid_cell"], row["frp"], row["confidence"], int(row["days"])
            score, count = int(row["score"]), int(row["detections"])
            lat, lon = float(row["latitude"]), float(row["longitude"])
            brightness = _finite(row["brightness"])
            satellites = sorted(label for column, label in satellite_columns.items() if row[column])
            events.append({
                "id": row["id"],
                "region": _region(lat, lon), "country": None, "latitude": round(lat, 5), "longitude": round(lon, 5),
                "category": "Requires Verification", "riskScore": score, "riskLevel": _level(score),
                "frp": round(frp, 2), "brightness": round(brightness, 1) if brightness is not None else None,
                "confidence": round(confidence), "persistenceDays": days, "detectionCount": count,
                "satellite": row["satellite"], "satellites": satellites,
                "daynight": str(row["daynight"]), "status": "CRITICAL" if score >= 76 else "HIGH RISK" if score >= 51 else "NEW",
                "acqDate": row["last_seen"], "history": history_by_cell[cell],
                "facility": None, "corroborated": count > 1,
                "riskSummary": "Prototype priority: 70% peak FRP (saturates at 100 MW), 30% normalized satellite confidence.",
                "reasons": [f"{count} satellite detections on {days} day(s) in the rolling window.",
                            "Thermal anomaly only; industrial/fire/flare/land-cover cause requires verification.",
                            "Country and district require boundary polygons; display regions are bounding extents."],
                "evidence": {"detections": count, "days": days,
                             "firstSeen": row["first_seen"], "lastSeen": row["last_seen"],
                             "maxFrp": round(frp, 2), "meanFrp": round(row["mean_frp"], 2),
                             "nightPasses": int(row["night_passes"]),
                             "lowConfidenceShare": round(row["low_share"], 3),
                             "meanConfidence": round(confidence, 1), "satellites": satellites},
            })
    events = _select_events(events, config.GLOBAL_MAX_EVENTS if max_events is None else max_events)
    facilities, places, context = load_references()
    enrich_context(events, facilities, places)
    weather_meta = enrich_weather(events, weather_provider, weather_limit)
    feeds = attrs.get("feeds", [])
    meta = {"source": attrs.get("source", "local_cache"), "scope": "global",
            "generatedAt": pd.Timestamp.now(tz="UTC").isoformat(), "events": len(events),
            "windowDays": attrs.get("window_hours", config.GLOBAL_FIRMS_WINDOW_HOURS) / 24,
            "coverage": "Worldwide satellite observations; cloud/overpass gaps apply. Countries and fire causes unverified.",
            "partial": bool(attrs.get("partial", False) or all_count > len(events)), "feeds": feeds,
            "observations": len(clean), "globalActiveHotspots": all_count, "exportedEvents": len(events),
            "omittedEvents": all_count - len(events), "sampling": "Priority per occupied 1-degree tile, then remaining priority; capped export",
            "totalGlobalFrpGw": round(total_frp / 1000, 6),
            "frpAggregation": "Sum of peak FRP per 0.01-degree event cell in rolling window, not simultaneous global power",
            "context": context, "cleaning": {**report, "input_rows": len(raw), "output_rows": len(clean),
                                               "dropped_invalid_frp_or_time": len(raw) - len(valid_raw)},
            "attribution": ["NASA FIRMS VIIRS active-fire observations"], **weather_meta}
    if not facilities.empty:
        meta["attribution"].append("WRI Global Power Plant Database (CC BY 4.0), static proximity context")
    if not places.empty:
        meta["attribution"].append("GeoNames (CC BY 4.0), nearest-city context")
    if weather_meta["weatherEnrichedEvents"]:
        meta["attribution"].append("Open-Meteo wind/weather, visual plume heuristic")
    return {"meta": meta, "events": events, "facilities": facilities_geojson(facilities)}


def run_global_pipeline(**kwargs) -> dict:
    return build_global_payload(fetch_global_hotspots(), **kwargs)
