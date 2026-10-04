"""Atomic compact global exports. National events.json is never a default target."""
from __future__ import annotations

import gzip
import json
import math
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import config

DEFAULT_OUTPUT = config.BASE_DIR / "holo-view-maker" / "public" / "data" / "global-events.json"


def _history_identity(event: dict) -> tuple | None:
    lat, lon = event.get("latitude"), event.get("longitude")
    if not isinstance(event.get("id"), str) or not event["id"]:
        return None
    if not all(isinstance(v, (float, int)) and not isinstance(v, bool) and math.isfinite(v) for v in (lat, lon)):
        return None
    if abs(lat) > 90 or abs(lon) > 180:
        return None
    return event["id"], math.floor(lon * 100), math.floor(lat * 100)


def _generated_day(value: str | None) -> int | None:
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is not None:
            stamp = stamp.astimezone(timezone.utc)
        return stamp.date().toordinal()
    except ValueError:
        return None


def _merge_snapshot_history(current: dict, previous: dict | None,
                            previous_generated_at: str | None = None) -> tuple[list, int]:
    from src.utils.export_3d_globe import _thermal_day, _thermal_group

    end = _thermal_day(current.get("acqDate"))
    current_rows = current.get("history") if isinstance(current.get("history"), list) else []
    if end is None:
        return list(current_rows), 0
    prior_rows = previous.get("history") if previous and isinstance(previous.get("history"), list) else []
    prior_end = _thermal_day(previous.get("acqDate")) if previous else None
    generated_day = _generated_day(previous_generated_at)
    if prior_end is not None and generated_day is not None:
        prior_end = min(prior_end, generated_day)
    if previous and previous.get("historyTruncated"):
        prior_rows = []
    merged, unmatched, rejected, blocked_days = {}, [], 0, set()
    for historical, rows in [(True, prior_rows), (False, current_rows)]:
        for row in rows:
            day = _thermal_day(row.get("date")) if isinstance(row, dict) else None
            if day is not None and (day < end - 30 or day > end):
                continue
            # Cached rows can supply only earlier baseline days. Current input
            # alone must establish current-day coverage and its daily peak.
            if historical and (prior_end is None or day is None or day >= end or day > prior_end):
                rejected += 1
                continue
            group = _thermal_group(row) if isinstance(row, dict) else None
            if day is None or group is None:
                if historical:
                    rejected += 1
                    if day is not None:
                        blocked_days.add(day)
                else:
                    unmatched.append(row)
                continue
            key = (day, group)
            frp, marker = row.get("frp"), row.get("frpObserved")
            valid = (isinstance(frp, (float, int)) and not isinstance(frp, bool) and math.isfinite(frp) and frp >= 0
                     and (marker is None or marker is True) and (frp != 0 or marker is True) and not row.get("synthetic"))
            candidate = dict(row) if valid else {**row, "frp": None, "frpObserved": False}
            existing = merged.get(key)
            # A partial/invalid group must survive dedupe, never become a lower
            # apparent daily peak after its missing observations are removed.
            if existing is None or candidate["frp"] is None:
                merged[key] = candidate
            elif existing["frp"] is not None and candidate["frp"] > existing["frp"]:
                merged[key] = candidate
    for key in list(merged):
        if key[0] in blocked_days:
            merged[key] = {**merged[key], "frp": None, "frpObserved": False}
    return [merged[key] for key in sorted(merged)] + unmatched, rejected


def _read_previous_snapshot(destination: Path) -> dict | None:
    if not destination.exists():
        return None

    def reject_constant(value):
        raise ValueError(f"non-JSON numeric constant {value}")

    try:
        previous = json.loads(destination.read_text(encoding="utf-8"), parse_constant=reject_constant)
        if (not isinstance(previous, dict) or not isinstance(previous.get("meta"), dict)
                or previous["meta"].get("source") not in ("firms_live", "local_cache", "mixed")
                or previous["meta"].get("scope", "global") != "global"
                or not isinstance(previous.get("events"), list)
                or not all(isinstance(e, dict) for e in previous["events"])):
            raise ValueError("unsupported global snapshot schema")
        return previous
    except (ValueError, OSError) as exc:
        raise ValueError(f"Previous global snapshot cannot be used: {exc}") from exc


def _atomic_bytes(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as file:
            temporary = Path(file.name)
            file.write(body)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def export_global_payload(payload: dict, destination: Path | str | None = None) -> Path:
    """Keep JSON for static hosts plus deterministic gzip for compatible consumers."""
    destination = Path(destination) if destination is not None else DEFAULT_OUTPUT
    if destination.name == "events.json":
        raise ValueError("Global export must not overwrite the national events.json")
    from src.utils.export_3d_globe import analyze_thermal_change

    json.dumps(payload, allow_nan=False)
    previous = _read_previous_snapshot(destination)
    previous_events = {_history_identity(e): e for e in previous["events"] if _history_identity(e) is not None} if previous else {}
    events, rejected_rows = [], 0
    for event in payload["events"]:
        history, rejected = _merge_snapshot_history(
            event, previous_events.get(_history_identity(event)),
            previous["meta"].get("generatedAt") if previous else None)
        enriched = {**event, "history": history}
        enriched["thermalChange"] = analyze_thermal_change(enriched)
        events.append(enriched)
        rejected_rows += rejected
    meta = {**payload["meta"],
            "historyScope": "Current selected cells only; daily sensor/pass history from selected snapshots, bounded to 30 prior days. Coverage is not continuous or planet-wide.",
            "historyRejectedRows": rejected_rows}
    body = json.dumps({"meta": meta, "events": events},
                      separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    facilities = json.dumps(payload.get("facilities", {"type": "FeatureCollection", "features": []}),
                            separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    # Validate and prepare every companion before touching the previous event snapshot.
    compressed = gzip.compress(body, mtime=0)
    _atomic_bytes(destination.with_suffix(".json.gz"), compressed)
    _atomic_bytes(destination.parent / "global-facilities.geojson", facilities)
    _atomic_bytes(destination, body)
    return destination
