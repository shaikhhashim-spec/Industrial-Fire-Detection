"""Build the India live-webcam link layer for the 3D globe from SkylineWebcams.

Reads SkylineWebcams' public India listing (one request; their robots.txt allows
it) and writes holo-view-maker/public/data/webcams.geojson: the webcam's name,
town and page URL. SkylineWebcams does not allow its pages to be embedded and
lists only a few Indian cameras, so the globe links out to their site and holds
no stream, image or player.

Usage:  .venv\\Scripts\\python scripts\\build_india_webcams.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.cameras.skyline import LISTING_URL, parse_listing, to_features

OUT = ROOT / "holo-view-maker" / "public" / "data" / "webcams.geojson"
PLACES = ROOT / "data" / "reference" / "india_places.csv"
UA = {"User-Agent": "SIH26162-thermal-intelligence/1.0 (student research project; link-out layer)"}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    page = requests.get(LISTING_URL, headers=UA, timeout=60)
    page.raise_for_status()
    entries = parse_listing(page.text)
    print(f"{len(entries)} India webcams on SkylineWebcams")
    if not entries:
        print("Found none. The page layout may have changed; leaving the existing layer untouched.")
        return 1

    places = pd.read_csv(PLACES)
    features, unplaced = to_features(entries, places)
    for name in unplaced:
        print(f"  no coordinates for '{name}': add its town to TOWN_CENTRES in src/cameras/skyline.py")
    if not features:
        return 1

    payload = {
        "type": "FeatureCollection",
        "meta": {
            "source": "SkylineWebcams India listing",
            "listing": LISTING_URL,
            "generatedAt": pd.Timestamp.now(tz="UTC").isoformat(),
            "count": len(features),
            "note": "Links only. SkylineWebcams does not allow embedding. Positions are town centres.",
        },
        "features": features,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    for f in features:
        p = f["properties"]
        print(f"  {p['name']}, {p['town']}, {p['state']} ({p['positionFrom']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
