"""Registry of live camera streams, pinned to coordinates inside India.

There is no public live CCTV feed covering the industrial sites this system
flags. Plant cameras are private security systems, the open aggregators list a
handful of tourism and weather cameras nationwide, and the only "industrial"
feeds reachable without permission are reachable because they are
misconfigured. So this module holds no feeds of its own: it is a table that
whoever actually has the access fills in, one row per camera, with the stream
URL they are entitled to publish.

Everything is validated against the same India boundaries the hotspot pipeline
uses, so a camera can never be registered outside the area this platform
covers.
"""
from __future__ import annotations

import json
import math
import re
import uuid
from typing import Any
from urllib.parse import parse_qs, urlparse

import config

EARTH_KM = 6371.0088

# How a browser has to play the URL. Inferred from the URL, overridable.
STREAM_TYPES = ("hls", "youtube", "mjpeg", "image", "iframe")

# A fixed camera sees a few hundred metres of useful detail; a tower-mounted
# one on a plant boundary sees a few km. The default is deliberately modest so
# coverage is not overclaimed.
DEFAULT_COVERAGE_KM = 3.0
MAX_COVERAGE_KM = 50.0

KINDS = ("Plant control room", "District authority", "Forest watchtower", "Traffic", "Other")

_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com"}


def infer_stream_type(url: str) -> str:
    """What a browser needs to do with this URL."""
    u = (url or "").strip().lower()
    host = urlparse(u).netloc
    if host in _YOUTUBE_HOSTS:
        return "youtube"
    if ".m3u8" in u:
        return "hls"
    if re.search(r"\.(mjpg|mjpeg)(\?|$)", u) or "mjpg" in u or "action=stream" in u:
        return "mjpeg"
    if re.search(r"\.(jpg|jpeg|png|webp)(\?|$)", u):
        return "image"
    return "iframe"


def youtube_embed(url: str) -> str | None:
    """The embeddable player URL for a YouTube watch or short link."""
    parsed = urlparse(url)
    if parsed.netloc not in _YOUTUBE_HOSTS:
        return None
    if parsed.netloc == "youtu.be":
        video_id = parsed.path.lstrip("/")
    elif parsed.path.startswith("/embed/"):
        return url
    elif parsed.path.startswith("/live/"):
        video_id = parsed.path.split("/live/", 1)[1].split("/")[0]
    else:
        video_id = (parse_qs(parsed.query).get("v") or [""])[0]
    video_id = video_id.split("?")[0].split("&")[0]
    return f"https://www.youtube.com/embed/{video_id}?autoplay=1&mute=1" if video_id else None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rad = math.pi / 180
    dlat = (lat2 - lat1) * rad
    dlon = (lon2 - lon1) * rad
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1 * rad) * math.cos(lat2 * rad) * math.sin(dlon / 2) ** 2
    )
    return 2 * EARTH_KM * math.asin(min(1.0, math.sqrt(h)))


def inside_india(lat: float, lon: float) -> bool:
    """Point-in-polygon against the same state boundaries that decide which
    hotspots this platform keeps, so "India only" means the same thing in both
    places. Falls back to the bounding box only if the boundary file is
    missing, and says so by being generous rather than silently rejecting."""
    bbox = config.INDIA_BBOX
    if not (bbox["min_lat"] <= lat <= bbox["max_lat"] and bbox["min_lon"] <= lon <= bbox["max_lon"]):
        return False
    try:
        import geopandas as gpd
        from shapely.geometry import Point

        from src.national.states import load_states

        states = load_states()
        return bool(states.contains(Point(lon, lat)).any()) or bool(
            gpd.GeoSeries([Point(lon, lat)], crs="EPSG:4326").intersects(states.union_all()).any()
        )
    except Exception:
        return True


def validate(camera: dict[str, Any]) -> list[str]:
    """Every reason this camera cannot be registered, in reading order."""
    problems: list[str] = []
    if not str(camera.get("name") or "").strip():
        problems.append("Give the camera a name, so it is identifiable in the coverage list.")

    try:
        lat = float(camera.get("latitude"))
        lon = float(camera.get("longitude"))
    except (TypeError, ValueError):
        problems.append("Latitude and longitude have to be numbers.")
        return problems

    if not inside_india(lat, lon):
        problems.append(
            f"{lat:.4f}, {lon:.4f} is outside India. This platform only covers Indian territory, "
            "and the hotspot pipeline drops anything outside it too."
        )

    url = str(camera.get("stream_url") or "").strip()
    if not url:
        problems.append("A stream URL is required.")
    elif not url.startswith(("http://", "https://")):
        problems.append("The stream URL has to start with http:// or https://.")
    elif url.startswith("http://"):
        problems.append(
            "This is an http:// URL. A browser on an https page will refuse to load it, so publish "
            "the stream over https or proxy it."
        )

    stream_type = camera.get("stream_type")
    if stream_type and stream_type not in STREAM_TYPES:
        problems.append(f"Unknown stream type {stream_type!r}. Expected one of {', '.join(STREAM_TYPES)}.")

    try:
        coverage = float(camera.get("coverage_km", DEFAULT_COVERAGE_KM))
        if not 0 < coverage <= MAX_COVERAGE_KM:
            problems.append(f"Coverage radius has to be between 0 and {MAX_COVERAGE_KM:.0f} km.")
    except (TypeError, ValueError):
        problems.append("Coverage radius has to be a number in kilometres.")

    return problems


def load() -> list[dict[str, Any]]:
    path = config.CAMERA_REGISTRY_PATH
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def save(cameras: list[dict[str, Any]]) -> None:
    path = config.CAMERA_REGISTRY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cameras, indent=2), encoding="utf-8")
    tmp.replace(path)


def add(camera: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    """Register one camera. Returns (stored_record, problems); on any problem
    nothing is written."""
    problems = validate(camera)
    if problems:
        return None, problems

    url = str(camera["stream_url"]).strip()
    record = {
        "id": str(camera.get("id") or f"CAM-{uuid.uuid4().hex[:6].upper()}"),
        "name": str(camera["name"]).strip(),
        "operator": str(camera.get("operator") or "").strip(),
        "kind": camera.get("kind") if camera.get("kind") in KINDS else "Other",
        "latitude": round(float(camera["latitude"]), 5),
        "longitude": round(float(camera["longitude"]), 5),
        "stream_url": url,
        "stream_type": camera.get("stream_type") or infer_stream_type(url),
        "coverage_km": round(float(camera.get("coverage_km", DEFAULT_COVERAGE_KM)), 2),
        "notes": str(camera.get("notes") or "").strip(),
        "active": bool(camera.get("active", True)),
    }
    cameras = [c for c in load() if c.get("id") != record["id"]]
    cameras.append(record)
    save(cameras)
    return record, []


def remove(camera_id: str) -> bool:
    cameras = load()
    kept = [c for c in cameras if c.get("id") != camera_id]
    if len(kept) == len(cameras):
        return False
    save(kept)
    return True


def set_active(camera_id: str, active: bool) -> bool:
    cameras = load()
    for camera in cameras:
        if camera.get("id") == camera_id:
            camera["active"] = active
            save(cameras)
            return True
    return False


def active_cameras() -> list[dict[str, Any]]:
    return [c for c in load() if c.get("active", True)]
