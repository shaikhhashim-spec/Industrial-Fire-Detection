"""Build the open-source reference layers that explain *why* a hotspot is where
it is. Run once (and occasionally to refresh); the pipeline reads the outputs
offline, so no page load or pipeline run depends on these services.

Outputs (data/reference/):
  india_facilities.geojson  point per known heat-producing facility:
      - OpenStreetMap via Overpass (ODbL): steel/iron works, non-renewable power
        plants, refineries and flares, cement, smelters, coal mines, brick kilns,
        chemical/fertilizer plants, other industrial works
      - WRI Global Power Plant Database v1.3 (CC BY 4.0): thermal power
        stations with capacity and fuel
  india_places.csv          GeoNames cities5000 (CC BY 4.0) for India, with
      state and district names — "12 km NW of Jamshedpur, Purbi Singhbhum"

Usage:  .venv\\Scripts\\python scripts\\build_india_reference.py
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import config

REF_DIR = ROOT / "data" / "reference"
RAW_DIR = config.CACHE_DIR / "reference"
UA = {"User-Agent": "SIH26162-thermal-intelligence/1.0 (research prototype; OSM/WRI/GeoNames reference build)"}

OVERPASS_MIRRORS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

# Split so no single query is heavy enough for a public Overpass server to refuse.
OVERPASS_QUERIES = {
    "plants_mines_kilns": """
        nwr["power"="plant"]["plant:source"!~"solar|wind|hydro|tidal"](area.in);
        nwr["man_made"~"^(flare|kiln)$"](area.in);
        nwr["landuse"="quarry"]["resource"~"coal|lignite"](area.in);
        nwr["landuse"="quarry"]["name"](area.in);
        nwr["industrial"~"^(mine|mining|coal_mine)$"](area.in);
    """,
    "works": """nwr["man_made"="works"](area.in);""",
    "industrial": """nwr["industrial"](area.in);""",
    # Big integrated sites (Bokaro Steel Plant, IISCO Burnpur, collieries) are
    # often only a *named* landuse=industrial area with no product tag.
    "named_heavy_industry": """
        nwr["landuse"="industrial"]["name"~"steel|ispat|iron|alumin|smelt|refiner|cement|thermal|power|coke|colliery|coal|fertili|petro",i](area.in);
    """,
}

WRI_URL = (
    "https://raw.githubusercontent.com/wri/global-power-plant-database/master/"
    "output_database/global_power_plant_database.csv"
)
THERMAL_FUELS = {"Coal", "Gas", "Oil", "Petcoke", "Biomass", "Waste", "Cogeneration", "Nuclear"}
GEONAMES = {
    "cities": "https://download.geonames.org/export/dump/cities5000.zip",
    "admin1": "https://download.geonames.org/export/dump/admin1CodesASCII.txt",
    "admin2": "https://download.geonames.org/export/dump/admin2Codes.txt",
}


def _get(url: str, **kw) -> requests.Response:
    for attempt in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=kw.pop("timeout", 120), **kw)
            r.raise_for_status()
            return r
        except requests.RequestException as exc:
            print(f"  retry {attempt + 1} for {url.split('/')[2]}: {exc}")
            time.sleep(4 * (attempt + 1))
    raise RuntimeError(f"download failed: {url}")


def overpass(name: str, body: str) -> list[dict]:
    cache = RAW_DIR / f"osm_{name}.json"
    if cache.exists() and time.time() - cache.stat().st_mtime < 7 * 86400:
        return json.loads(cache.read_text(encoding="utf-8"))["elements"]
    query = f"""[out:json][timeout:300];
area["ISO3166-1"="IN"]["admin_level"="2"]->.in;
({body});
out center tags;"""
    for url in OVERPASS_MIRRORS:
        try:
            print(f"  overpass {name} via {url.split('/')[2]} …")
            r = requests.post(url, data={"data": query}, headers=UA, timeout=360)
            if r.status_code != 200 or not r.text.lstrip().startswith("{"):
                print(f"    HTTP {r.status_code}: {r.text[:120]!r}")
                continue
            data = r.json()
            if data.get("remark", "").lower().startswith("runtime error"):
                print(f"    {data['remark'][:120]}")
                continue
            cache.write_text(json.dumps(data), encoding="utf-8")
            return data["elements"]
        except (requests.RequestException, ValueError) as exc:
            print(f"    failed: {exc}")
        time.sleep(5)
    raise RuntimeError(f"all Overpass mirrors failed for {name}")


def classify_osm(tags: dict) -> tuple[str, str] | None:
    """(kind, detail) for an OSM element, or None if not a plausible heat source."""
    t = {k: str(v).lower() for k, v in tags.items()}
    product = t.get("product", "")
    industrial = t.get("industrial", "")
    name = t.get("name:en", t.get("name", ""))
    power_src = t.get("plant:source", "") or t.get("generator:source", "")

    if t.get("power") == "plant":
        return "thermal power plant", f"{power_src or 'unspecified fuel'} power plant"
    if t.get("man_made") == "flare" or industrial in ("refinery", "oil", "gas", "petrochemical", "oil_refinery") or any(
        s in name for s in ("refinery", "petrochemical")
    ):
        return "refinery / oil & gas", industrial or ("gas flare" if t.get("man_made") == "flare" else "refinery")
    if any(s in product for s in ("steel", "iron", "sponge")) or industrial in (
        "steelmaking", "steel_mill", "steelworks", "iron_works", "ironworks", "steel", "foundry", "metallurgy",
    ) or any(s in name for s in (" steel", "ispat", "steel plant", "iron ore")):
        return "steel / iron works", product or industrial or "steel works"
    if "cement" in product or industrial == "cement" or "cement" in name:
        return "cement plant", "cement"
    if industrial in ("smelter", "aluminium_smelter", "aluminum_smelter") or any(
        s in product for s in ("aluminium", "aluminum", "copper", "zinc", "alumina")
    ):
        return "smelter", product or industrial
    if t.get("landuse") == "quarry" and t.get("resource", "") in ("coal", "lignite"):
        return "coal mine", t["resource"]
    if any(s in name for s in ("colliery", "coal mine", "coalfield", "coal field", "opencast", " ocp")):
        return "coal mine", "colliery"
    if any(s in name for s in ("thermal power", "power station", "power plant", " tps", "stps")):
        return "thermal power plant", "power station"
    if "coke" in name:
        return "coke oven", "coke"
    if industrial in ("mine", "mining", "coal_mine"):
        return "coal mine" if "coal" in (t.get("resource", "") + name) else "mine / quarry", industrial
    if t.get("man_made") == "kiln" or industrial in ("brickworks", "brickyard", "brick_kiln") or "brick" in product:
        return "brick kiln", "brick kiln"
    if industrial in ("chemical", "fertilizer", "fertiliser") or any(
        s in product or s in name for s in ("fertili", "chemical")
    ):
        return "chemical / fertilizer plant", industrial or product or "fertilizer / chemical"
    if t.get("landuse") == "quarry":
        return "mine / quarry", t.get("resource", "") or "quarry"
    if "coke" in product or industrial == "coke":
        return "coke oven", "coke"
    if t.get("man_made") == "works" or industrial or t.get("landuse") == "industrial":
        return "industrial works", product or industrial or "industrial area"
    return None


# Sites that produce no meaningful heat — their labels only clutter the map and
# would wrongly "explain" a hotspot (bus depots, warehouses, godowns, ports…).
NON_THERMAL_DETAIL = {
    "depot", "bus_depot", "warehouse", "port", "scrap_yard", "slaughterhouse", "storage", "distributor",
    "pump_house", "logistics", "agriculture", "poultry_farm", "furniture", "grinding_mill", "flour",
    "sawmill", "oxygen", "oil_storage", "water", "water_works", "wastewater_plant", "machinery",
}
NON_THERMAL_NAME = re.compile(
    r"depot|warehouse|godown|godam|workshop|garage|\bstore\b|bus stand|metro|service station|showroom|"
    r"shipyard|timber|cycle|tyre|auto ",
    re.I,
)


def relevant(name: str, kind: str, detail: str) -> bool:
    """Named, and plausibly a source of heat a satellite could see."""
    if not name.strip():
        return False
    if kind == "industrial works" and (detail in NON_THERMAL_DETAIL or NON_THERMAL_NAME.search(name)):
        return False
    return not NON_THERMAL_NAME.search(name) or kind in ("thermal power plant", "steel / iron works")


def build_facilities() -> None:
    features: list[dict] = []
    seen: set[str] = set()
    for name, body in OVERPASS_QUERIES.items():
        try:
            elements = overpass(name, body)
        except RuntimeError as exc:
            print(f"  ! {exc} — continuing without this group")
            continue
        for el in elements:
            ref = f"{el['type']}/{el['id']}"
            if ref in seen:
                continue
            lat = el.get("lat", el.get("center", {}).get("lat"))
            lon = el.get("lon", el.get("center", {}).get("lon"))
            tags = el.get("tags", {})
            kind = classify_osm(tags)
            if lat is None or lon is None or kind is None:
                continue
            if not relevant(tags.get("name:en") or tags.get("name") or "", kind[0], str(kind[1]).lower()):
                continue
            seen.add(ref)
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [round(lon, 5), round(lat, 5)]},
                "properties": {
                    "name": tags.get("name:en") or tags.get("name") or "",
                    "kind": kind[0],
                    "detail": kind[1],
                    "operator": tags.get("operator", ""),
                    "capacity_mw": None,
                    "source": "OpenStreetMap",
                    "ref": ref,
                    "url": f"https://www.openstreetmap.org/{ref}",
                },
            })
        print(f"  OSM {name}: {len(elements)} elements → {len(features)} facilities so far")

    print("  WRI Global Power Plant Database …")
    wri = pd.read_csv(io.StringIO(_get(WRI_URL, timeout=180).text), low_memory=False)
    wri = wri[(wri["country"] == "IND") & (wri["primary_fuel"].isin(THERMAL_FUELS))]
    for _, r in wri.iterrows():
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(float(r["longitude"]), 5), round(float(r["latitude"]), 5)]},
            "properties": {
                "name": r["name"],
                "kind": "thermal power plant",
                "detail": f"{r['primary_fuel'].lower()} power plant",
                "operator": r.get("owner") if isinstance(r.get("owner"), str) else "",
                "capacity_mw": float(r["capacity_mw"]) if pd.notna(r["capacity_mw"]) else None,
                "source": "WRI Global Power Plant Database",
                "ref": r["gppd_idnr"],
                "url": r["url"] if isinstance(r.get("url"), str) else "https://datasets.wri.org/dataset/globalpowerplantdatabase",
            },
        })
    print(f"  WRI: {len(wri)} thermal plants in India")

    out = {
        "type": "FeatureCollection",
        "attribution": "© OpenStreetMap contributors (ODbL); WRI Global Power Plant Database v1.3 (CC BY 4.0)",
        "generated": pd.Timestamp.now(tz="UTC").isoformat(),
        "features": features,
    }
    path = REF_DIR / "india_facilities.geojson"
    path.write_text(json.dumps(out), encoding="utf-8")
    kinds = pd.Series([f["properties"]["kind"] for f in features]).value_counts()
    print(f"→ {path.name}: {len(features)} facilities\n{kinds.to_string()}")


def build_places() -> None:
    print("  GeoNames cities5000 + admin names …")
    z = zipfile.ZipFile(io.BytesIO(_get(GEONAMES["cities"], timeout=180).content))
    cols = ["geonameid", "name", "asciiname", "alt", "lat", "lon", "fclass", "fcode", "cc", "cc2",
            "admin1", "admin2", "admin3", "admin4", "population", "elev", "dem", "tz", "modified"]
    cities = pd.read_csv(z.open("cities5000.txt"), sep="\t", names=cols, dtype={"admin1": str, "admin2": str},
                         keep_default_na=False, quoting=3)
    cities = cities[cities["cc"] == "IN"]
    a1 = pd.read_csv(io.StringIO(_get(GEONAMES["admin1"]).text), sep="\t", names=["code", "name", "ascii", "id"],
                     keep_default_na=False, quoting=3)
    a2 = pd.read_csv(io.StringIO(_get(GEONAMES["admin2"]).text), sep="\t", names=["code", "name", "ascii", "id"],
                     keep_default_na=False, quoting=3)
    a1_map = dict(zip(a1["code"], a1["ascii"]))
    a2_map = dict(zip(a2["code"], a2["ascii"]))
    places = pd.DataFrame({
        "name": cities["asciiname"],
        "lat": cities["lat"].astype(float),
        "lon": cities["lon"].astype(float),
        "population": pd.to_numeric(cities["population"], errors="coerce").fillna(0).astype(int),
        "state": [a1_map.get(f"IN.{c}", "") for c in cities["admin1"]],
        "district": [a2_map.get(f"IN.{c1}.{c2}", "") for c1, c2 in zip(cities["admin1"], cities["admin2"])],
    })
    path = REF_DIR / "india_places.csv"
    places.to_csv(path, index=False)
    print(f"→ {path.name}: {len(places)} places ({(places['district'] != '').mean():.0%} with district)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252
    REF_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    build_places()
    build_facilities()
