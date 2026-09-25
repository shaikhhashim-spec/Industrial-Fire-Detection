"""Build the India CCTV camera layer for the 3D globe from OpenStreetMap.

OpenStreetMap volunteers have mapped roughly nine thousand public-space cameras
across India (man_made=surveillance): where each one is, what it watches, how it
is mounted and which way it faces. That is the only openly published camera data
for the whole country. Government and plant CCTV feeds are private, so this layer
holds locations and tags only, never video, and it does not touch any camera.

Every point is kept only if it falls inside an Indian state polygon, the same
"India only" rule the hotspot pipeline uses, and gets its state name.

Output: holo-view-maker/public/data/cameras.geojson (ODbL, © OpenStreetMap
contributors). Refresh it whenever you like; the globe reads it as a static file.

Usage:  .venv\\Scripts\\python scripts\\build_india_cameras.py [--refresh]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import config
from src.cameras.osm_cameras import KINDS, to_features
from src.national.states import assign_state

OUT = ROOT / "holo-view-maker" / "public" / "data" / "cameras.geojson"
RAW = config.CACHE_DIR / "reference" / "osm_cameras.json"
UA = {"User-Agent": "SIH26162-thermal-intelligence/1.0 (research prototype; OSM camera layer build)"}
MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
QUERY = """[out:json][timeout:240];
area["ISO3166-1"="IN"]["admin_level"="2"]->.in;
node["man_made"="surveillance"](area.in);
out body;"""


def fetch(refresh: bool) -> dict:
    if RAW.exists() and not refresh and time.time() - RAW.stat().st_mtime < 7 * 86400:
        print(f"using cached Overpass response ({RAW.name})")
        return json.loads(RAW.read_text(encoding="utf-8"))
    for url in MIRRORS:
        try:
            print(f"querying {url.split('/')[2]} ...")
            r = requests.post(url, data={"data": QUERY}, headers=UA, timeout=300)
            if r.status_code != 200 or not r.text.lstrip().startswith("{"):
                print(f"  HTTP {r.status_code}: {r.text[:100]!r}")
                continue
            data = r.json()
            if str(data.get("remark", "")).lower().startswith("runtime error") or not data.get("elements"):
                print(f"  no usable result: {str(data.get('remark', ''))[:100]}")
                continue
            RAW.parent.mkdir(parents=True, exist_ok=True)
            RAW.write_text(json.dumps(data), encoding="utf-8")
            return data
        except (requests.RequestException, ValueError) as exc:
            print(f"  failed: {exc}")
        time.sleep(5)
    raise RuntimeError("every Overpass mirror failed; try again in a few minutes")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", action="store_true", help="ignore the cached Overpass response")
    args = ap.parse_args()

    data = fetch(args.refresh)
    elements = data["elements"]
    features = to_features(elements)
    print(f"{len(elements):,} OSM surveillance nodes, {len(features):,} public-space cameras")

    coords = pd.DataFrame(
        {
            "longitude": [f["geometry"]["coordinates"][0] for f in features],
            "latitude": [f["geometry"]["coordinates"][1] for f in features],
        }
    )
    states = assign_state(coords)["state"].tolist()
    kept = []
    for feature, state in zip(features, states):
        if not isinstance(state, str) or not state:
            continue  # outside every Indian state polygon
        feature["properties"]["state"] = state
        kept.append(feature)
    print(f"{len(kept):,} inside India ({len(features) - len(kept):,} dropped outside the state boundaries)")

    if len(kept) < 500:
        print("Refusing to overwrite the layer with a suspiciously small result.")
        return 1

    kinds = Counter(f["properties"]["kind"] for f in kept)
    payload = {
        "type": "FeatureCollection",
        "meta": {
            "source": "OpenStreetMap, man_made=surveillance",
            "license": "ODbL 1.0, © OpenStreetMap contributors",
            "osmTimestamp": data.get("osm3s", {}).get("timestamp_osm_base"),
            "generatedAt": pd.Timestamp.now(tz="UTC").isoformat(),
            "count": len(kept),
            "withHeading": sum("heading" in f["properties"] for f in kept),
            "kinds": {k: kinds.get(k, 0) for k in KINDS},
        },
        "features": kept,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1e6:.2f} MB)")
    print("by what they watch:", dict(kinds.most_common()))
    print("with a mapped heading:", payload["meta"]["withHeading"])
    print("top states:", dict(Counter(f["properties"]["state"] for f in kept).most_common(8)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
