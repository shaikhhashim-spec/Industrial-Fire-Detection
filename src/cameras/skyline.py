"""India live webcams listed on SkylineWebcams, for the globe's link-out layer.

SkylineWebcams is a tourism webcam site. Its India page lists only a handful of
cameras, and it sends X-Frame-Options: SAMEORIGIN, i.e. it does not permit its
pages to be embedded elsewhere. So this layer only *links* to their pages: it
holds the webcam's name, town and page URL, never a stream, an image or a
player. A visitor watches on their site.

Their pages publish no coordinates, so each webcam is placed at the centre of
its town (GeoNames, else a small OpenStreetMap override table). The position is
therefore the town, not the camera, and the layer labels it that way.
"""
from __future__ import annotations

import html
import re
from typing import Any

import pandas as pd

SITE = "https://www.skylinewebcams.com/"
LISTING_URL = SITE + "en/webcam/india.html"

# <a href="en/webcam/india/<state>/<town>/<slug>.html"> ... <p class="tcam">Name</p><p class="subt">About</p>
_ENTRY = re.compile(
    r'<a href="(en/webcam/india/([a-z0-9-]+)/([a-z0-9-]+)/([a-z0-9-]+)\.html)"[^>]*>'
    r'.*?<p class="tcam">(.*?)</p>(?:<p class="subt">(.*?)</p>)?',
    re.S,
)
_TAGS = re.compile(r"<[^>]+>")

# Towns too small for the GeoNames table (cities of 5,000+). Centre of the
# OpenStreetMap place=town node.
TOWN_CENTRES: dict[tuple[str, str], tuple[float, float]] = {
    ("rajasthan", "mount-abu"): (24.592433, 72.708188),
}


def slug_to_name(slug: str) -> str:
    return " ".join(part.capitalize() for part in slug.split("-"))


def _text(fragment: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAGS.sub("", fragment or ""))).strip()


def parse_listing(page: str) -> list[dict[str, str]]:
    """The webcams on the India listing page, in page order."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for path, state_slug, town_slug, slug, name, about in _ENTRY.findall(page):
        if slug in seen:
            continue
        seen.add(slug)
        out.append(
            {
                "id": slug,
                "name": _text(name),
                "about": _text(about),
                "state": slug_to_name(state_slug),
                "town": slug_to_name(town_slug),
                "stateSlug": state_slug,
                "townSlug": town_slug,
                "url": SITE + path,
            }
        )
    return out


def locate(entry: dict[str, str], places: pd.DataFrame) -> tuple[float, float, str] | None:
    """(lat, lon, where it came from) for the webcam's town, or None."""
    override = TOWN_CENTRES.get((entry["stateSlug"], entry["townSlug"]))
    if override:
        return override[0], override[1], "OpenStreetMap place=town"
    if places.empty:
        return None
    match = places[
        (places["name"].str.lower() == entry["town"].lower())
        & (places["state"].str.lower() == entry["state"].lower())
    ]
    if match.empty:
        return None
    row = match.sort_values("population", ascending=False).iloc[0]
    return float(row["lat"]), float(row["lon"]), "GeoNames"


def to_features(entries: list[dict[str, str]], places: pd.DataFrame) -> tuple[list[dict[str, Any]], list[str]]:
    """GeoJSON points for the webcams that could be placed, plus the names of the
    ones that could not (so the build can say what needs a coordinate)."""
    features: list[dict[str, Any]] = []
    unplaced: list[str] = []
    for entry in entries:
        found = locate(entry, places)
        if found is None:
            unplaced.append(entry["name"])
            continue
        lat, lon, source = found
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
                "properties": {
                    "id": entry["id"],
                    "name": entry["name"],
                    "about": entry["about"],
                    "town": entry["town"],
                    "state": entry["state"],
                    "url": entry["url"],
                    "positionFrom": f"town centre, {source}",
                },
            }
        )
    return features, unplaced
