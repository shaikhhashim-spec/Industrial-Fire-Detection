"""Atomic compact global exports. National events.json is never a default target."""
from __future__ import annotations

import gzip
import json
import os
import tempfile
from pathlib import Path

import config

DEFAULT_OUTPUT = config.BASE_DIR / "holo-view-maker" / "public" / "data" / "global-events.json"


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
    body = json.dumps({"meta": payload["meta"], "events": payload["events"]},
                      separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    facilities = json.dumps(payload.get("facilities", {"type": "FeatureCollection", "features": []}),
                            separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")
    # Validate and prepare every companion before touching the previous event snapshot.
    compressed = gzip.compress(body, mtime=0)
    _atomic_bytes(destination.with_suffix(".json.gz"), compressed)
    _atomic_bytes(destination.parent / "global-facilities.geojson", facilities)
    _atomic_bytes(destination, body)
    return destination
