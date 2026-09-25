"""Turn OpenStreetMap surveillance nodes into the compact camera layer the globe draws.

This is the only openly published, nationwide camera data for India: locations
that volunteers have mapped, with what the camera looks at, how it is mounted
and which way it faces. It carries no video. Nothing here contacts a camera or
a stream; it only reads OSM tags.

The layer covers public space on purpose. Cameras tagged private, indoor or as
a doorbell are dropped (they are someone's home or shop, and nothing about a
fire depends on them), and so are guard posts and viewpoints, which OSM files
under the same tag but which are not cameras.
"""
from __future__ import annotations

import re
from typing import Any

# What a camera watches, from surveillance:zone. Order is the legend order.
KINDS = ("Traffic", "Streets and public spaces", "Buildings", "Open areas", "Unspecified")

_ZONE_KIND = {
    "traffic": "Traffic",
    "town": "Streets and public spaces",
    "street": "Streets and public spaces",
    "public": "Streets and public spaces",
    "building": "Buildings",
    "entrance": "Buildings",
    "shop": "Buildings",
    "parking": "Traffic",
    "area": "Open areas",
    "yes": "Unspecified",
}

_COMPASS = {
    "n": 0, "nne": 22.5, "ne": 45, "ene": 67.5, "e": 90, "ese": 112.5, "se": 135, "sse": 157.5,
    "s": 180, "ssw": 202.5, "sw": 225, "wsw": 247.5, "w": 270, "wnw": 292.5, "nw": 315, "nnw": 337.5,
    "north": 0, "northeast": 45, "east": 90, "southeast": 135, "south": 180,
    "southwest": 225, "west": 270, "northwest": 315,
}

_CAMERA_TYPES = {"fixed", "dome", "panning", "panorama"}
_MOUNTS = {"pole", "wall", "ceiling", "gantry", "building", "traffic_signals", "street_lamp", "roof"}

# Cameras whose location says nothing useful for a public-safety layer.
_EXCLUDED_SURVEILLANCE = {"private", "indoor"}
_NOT_CAMERAS = {"guard", "viewpoint"}


def parse_direction(raw: Any) -> float | None:
    """Degrees clockwise from north, from '90', '270.5', 'NE' or 'southwest'.
    Values OSM allows but that are not one direction (ranges, lists) return None."""
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if not text:
        return None
    if text in _COMPASS:
        return float(_COMPASS[text])
    if re.fullmatch(r"-?\d+(\.\d+)?", text):
        return round(float(text) % 360, 1)
    return None


def parse_angle(raw: Any) -> float | None:
    """Field of view in degrees from camera:angle, when it is a sane number."""
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return round(value, 1) if 5 <= value <= 360 else None


def _first_value(raw: Any) -> str | None:
    """OSM joins alternatives with ';'. Keep the first."""
    if raw is None:
        return None
    first = str(raw).split(";")[0].strip().lower()
    return first or None


def classify_kind(tags: dict[str, str]) -> str:
    zone = _first_value(tags.get("surveillance:zone"))
    if zone in _ZONE_KIND:
        return _ZONE_KIND[zone]
    if _first_value(tags.get("surveillance")) == "traffic":
        return "Traffic"
    return "Unspecified"


def _clean(text: Any, limit: int = 80) -> str | None:
    if text is None:
        return None
    out = re.sub(r"\s+", " ", str(text)).strip()
    return out[:limit] if out else None


def keep(tags: dict[str, str]) -> bool:
    """A public-space camera. False for private, indoor and doorbell cameras and for
    OSM's guard posts and viewpoints."""
    if tags.get("man_made") != "surveillance":
        return False
    if _first_value(tags.get("surveillance")) in _EXCLUDED_SURVEILLANCE:
        return False
    types = {t.strip().lower() for t in str(tags.get("surveillance:type") or "").split(";")}
    if types and types <= _NOT_CAMERAS:
        return False
    camera_type = _first_value(tags.get("camera:type"))
    if camera_type == "doorbell":
        return False
    if _first_value(tags.get("level")) not in (None, "0"):
        return False  # upper floors of a building are indoors in practice
    return True


def to_feature(element: dict[str, Any]) -> dict[str, Any] | None:
    """One Overpass node as a GeoJSON point with the few fields the globe uses,
    or None when the node is not a public-space camera."""
    tags = element.get("tags") or {}
    if element.get("type") != "node" or not keep(tags):
        return None
    try:
        lat, lon = float(element["lat"]), float(element["lon"])
    except (KeyError, TypeError, ValueError):
        return None

    camera_type = _first_value(tags.get("camera:type"))
    mount = _first_value(tags.get("camera:mount"))
    types = {t.strip().lower() for t in str(tags.get("surveillance:type") or "").split(";")}

    props: dict[str, Any] = {
        "id": int(element["id"]),
        "kind": classify_kind(tags),
        "type": camera_type if camera_type in _CAMERA_TYPES else None,
        "mount": mount if mount in _MOUNTS else None,
        "heading": parse_direction(tags.get("camera:direction") or tags.get("direction")),
        "angle": parse_angle(tags.get("camera:angle")),
        "plateReader": "alpr" in types,
        "operator": _clean(tags.get("operator") or tags.get("network"), 60),
        "name": _clean(tags.get("name") or tags.get("ref") or tags.get("description"), 80),
    }
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
        "properties": {k: v for k, v in props.items() if v is not None and v is not False},
    }


def to_features(elements: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """All public-space cameras, one feature per OSM node id."""
    seen: set[int] = set()
    out: list[dict[str, Any]] = []
    for el in elements:
        feature = to_feature(el)
        if feature is None:
            continue
        node_id = feature["properties"]["id"]
        if node_id in seen:
            continue
        seen.add(node_id)
        out.append(feature)
    return out
