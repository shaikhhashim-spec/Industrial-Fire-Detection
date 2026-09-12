"""Open-source context for national hotspot events: the "why is this point
here" layer.

Every event gets:
  * the nearest known heat-producing facility (OpenStreetMap + WRI Global
    Power Plant Database, built by scripts/build_india_reference.py),
  * the nearest town and its district (GeoNames),
  * an explainable category, and
  * plain-language reasons combining that context with the satellite evidence
    (how many days it was seen, heat output, night passes, FIRMS confidence).

Honest by construction: a facility is only credited when one is mapped within
FACILITY_RADIUS_KM, and anything the evidence can't settle stays "Requires
Verification" with the reason spelled out, rather than a confident guess.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache

import numpy as np
import pandas as pd

import config

FACILITIES_PATH = config.BASE_DIR / "data" / "reference" / "india_facilities.geojson"
PLACES_PATH = config.BASE_DIR / "data" / "reference" / "india_places.csv"
EARTH_KM = 6371.0088

# A VIIRS I-band pixel is 375 m, and a steel works, coalfield or refinery spans
# several km, so 3 km attributes a detection to a site without reaching the next town.
FACILITY_RADIUS_KM = 3.0
MENTION_RADIUS_KM = 10.0

# Most- to least-specific explanation of heat; the best-ranked facility inside
# the radius wins over a merely closer generic one.
KIND_PRIORITY = [
    "steel / iron works", "thermal power plant", "refinery / oil & gas", "smelter", "coke oven",
    "cement plant", "coal mine", "brick kiln", "chemical / fertilizer plant", "mine / quarry",
    "industrial works",
]
HIGH_HEAT_KINDS = set(KIND_PRIORITY[:8])
FLARE_KINDS = {"refinery / oil & gas"}

# Crop-residue burning windows (months) by state. Seasonal hints only.
AGRI_BURN_SEASONS = {
    "Punjab": {4, 5, 10, 11}, "Haryana": {4, 5, 10, 11}, "Uttar Pradesh": {4, 5, 10, 11},
    "Madhya Pradesh": {3, 4, 5}, "Rajasthan": {3, 4, 5}, "Bihar": {4, 5},
    "Mizoram": {2, 3, 4}, "Manipur": {2, 3, 4}, "Nagaland": {2, 3, 4}, "Meghalaya": {2, 3, 4},
    "Tripura": {2, 3, 4}, "Arunachal Pradesh": {2, 3, 4}, "Assam": {2, 3, 4},
}
MONTHS = ["", "January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]
COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


@lru_cache(maxsize=1)
def _facilities() -> pd.DataFrame:
    if not FACILITIES_PATH.exists():
        return pd.DataFrame(columns=["lat", "lon", "name", "kind", "detail", "operator", "capacity_mw",
                                     "source", "ref", "url"])
    data = json.loads(FACILITIES_PATH.read_text(encoding="utf-8"))
    rows = [{"lon": f["geometry"]["coordinates"][0], "lat": f["geometry"]["coordinates"][1], **f["properties"]}
            for f in data["features"]]
    df = pd.DataFrame(rows)
    df["priority"] = df["kind"].map({k: i for i, k in enumerate(KIND_PRIORITY)}).fillna(len(KIND_PRIORITY))
    return df


@lru_cache(maxsize=1)
def _places() -> pd.DataFrame:
    if not PLACES_PATH.exists():
        return pd.DataFrame(columns=["name", "lat", "lon", "population", "state", "district"])
    return pd.read_csv(PLACES_PATH, keep_default_na=False)


def _tree(df: pd.DataFrame):
    from sklearn.neighbors import BallTree

    return BallTree(np.radians(df[["lat", "lon"]].to_numpy(dtype=float)), metric="haversine")


def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    """Compass direction of point 2 as seen from point 1."""
    φ1, φ2 = math.radians(lat1), math.radians(lat2)
    dλ = math.radians(lon2 - lon1)
    y = math.sin(dλ) * math.cos(φ2)
    x = math.cos(φ1) * math.sin(φ2) - math.sin(φ1) * math.cos(φ2) * math.cos(dλ)
    return COMPASS[round(((math.degrees(math.atan2(y, x)) + 360) % 360) / 45) % 8]


def _capacity(f: dict) -> float | None:
    cap = f.get("capacity_mw")
    return float(cap) if cap is not None and pd.notna(cap) and cap > 0 else None


def _facility_label(f: dict) -> str:
    bits = [f["kind"]]
    if cap := _capacity(f):
        bits = [f"{cap:,.0f} MW {f['detail']}"]
    if f.get("operator"):
        bits.append(f"operator {f['operator']}")
    return ", ".join(bits)


def _source_label(f: dict) -> str:
    return f"{f['source']} {f['ref']}" if f["source"] == "OpenStreetMap" else f"WRI GPPD {f['ref']}"


def enrich_events(events: pd.DataFrame, detail: pd.DataFrame | None = None) -> pd.DataFrame:
    """Add place / facility / category / reasons / evidence columns to the
    national events frame (one row per grid cell)."""
    if events.empty:
        return events
    ev = events.copy()
    pts = np.radians(ev[["latitude", "longitude"]].to_numpy(dtype=float))

    # ── nearest town (always) ──
    places = _places()
    place_cols = {"place_name": "", "place_km": np.nan, "place_dir": "", "district": ""}
    for c, v in place_cols.items():
        ev[c] = v
    if not places.empty:
        dist, idx = _tree(places).query(pts, k=1)
        near = places.iloc[idx[:, 0]].reset_index(drop=True)
        ev["place_name"] = near["name"].to_numpy()
        ev["place_km"] = (dist[:, 0] * EARTH_KM).round(1)
        ev["district"] = near["district"].to_numpy()
        ev["place_dir"] = [
            _bearing(p_lat, p_lon, e_lat, e_lon)
            for p_lat, p_lon, e_lat, e_lon in zip(near["lat"], near["lon"], ev["latitude"], ev["longitude"])
        ]

    # ── facilities within MENTION_RADIUS_KM: best-ranked inside the attribution radius ──
    fac = _facilities()
    best: list[dict | None] = [None] * len(ev)
    nearest_any: list[dict | None] = [None] * len(ev)
    if not fac.empty:
        ind, dist = _tree(fac).query_radius(pts, r=MENTION_RADIUS_KM / EARTH_KM, return_distance=True,
                                            sort_results=True)
        records = fac.to_dict("records")
        for i, (ids, ds) in enumerate(zip(ind, dist)):
            if len(ids) == 0:
                continue
            cands = [{**records[j], "km": float(d * EARTH_KM)} for j, d in zip(ids, ds)]
            nearest_any[i] = cands[0]
            inside = [c for c in cands if c["km"] <= FACILITY_RADIUS_KM]
            if inside:
                best[i] = min(inside, key=lambda c: (c["priority"], c["km"]))

    # ── per-cell detection evidence from the observation rows ──
    evidence_by_cell: dict[str, dict] = {}
    if detail is not None and not detail.empty and "grid_cell" in detail.columns:
        d = detail.copy()
        d["acq_date"] = pd.to_datetime(d["acq_date"])
        daynight = d["daynight"] if "daynight" in d.columns else pd.Series("D", index=d.index)
        d["is_night"] = daynight.astype(str).str.upper().eq("N")
        conf = d["confidence"].astype(str).str.lower() if "confidence" in d.columns else pd.Series("n", index=d.index)
        d["is_low"] = conf.isin(["l", "low"])
        for cell, g in d.groupby("grid_cell"):
            evidence_by_cell[str(cell)] = {
                "detections": len(g),
                "days": int(g["acq_date"].dt.normalize().nunique()),
                "firstSeen": g["acq_date"].min().date().isoformat(),
                "lastSeen": g["acq_date"].max().date().isoformat(),
                "maxFrp": round(float(g["frp"].max()), 1),
                "meanFrp": round(float(g["frp"].mean()), 1),
                "nightPasses": int(g["is_night"].sum()),
                "lowConfidenceShare": round(float(g["is_low"].mean()), 2),
                "meanConfidence": round(float(g.get("confidence_numeric", pd.Series([np.nan])).mean()), 0),
                "satellites": sorted({_sat_name(s) for s in g.get("satellite", pd.Series(dtype=str)).astype(str)}),
            }

    window = config.NATIONAL_HISTORY_DAYS
    cats, reasons_col, evidence_col, facility_col, corroborated_col = [], [], [], [], []
    for i, row in enumerate(ev.itertuples(index=False)):
        r = row._asdict()
        e = evidence_by_cell.get(str(r.get("grid_cell")), {
            "detections": int(r.get("observation_count", 1)), "days": int(r.get("persistence_days", 1)),
            "firstSeen": None, "lastSeen": None, "maxFrp": round(float(r.get("max_frp", 0)), 1),
            "meanFrp": round(float(r.get("avg_frp", 0)), 1), "nightPasses": 0, "lowConfidenceShare": 0.0,
            "meanConfidence": round(float(r.get("avg_confidence", 0)), 0), "satellites": [],
        })
        f = best[i]
        state = r["state"] if isinstance(r.get("state"), str) and r["state"] else "India"
        persistent = bool(r.get("is_persistent")) or e["days"] >= config.NATIONAL_PERSISTENCE_MIN_DAYS_HISTORY
        month = pd.to_datetime(e["lastSeen"]).month if e["lastSeen"] else pd.Timestamp.now().month
        day_only = e["nightPasses"] == 0
        all_low = e["lowConfidenceShare"] >= 0.99
        agri = month in AGRI_BURN_SEASONS.get(state, set())

        # ── category (explainable rules, most specific first) ──
        if f and f["kind"] in HIGH_HEAT_KINDS:
            if persistent:
                cat, why = "Persistent Industrial Activity", f"recurring heat at a mapped {f['kind']}"
            elif f["kind"] in FLARE_KINDS:
                cat, why = "Transient Industrial Flare", f"intermittent heat at a {f['kind']} site (flaring pattern)"
            elif e["maxFrp"] >= config.FRP_HIGH_MIN:
                cat, why = "Likely Industrial Fire", f"strong heat at a {f['kind']}, not a recurring signal"
            else:
                cat, why = "Requires Verification", f"weak one-off signal next to a {f['kind']}, which could be routine activity"
        elif f:
            cat, why = (("Persistent Industrial Activity", f"recurring heat at mapped {f['kind']}") if persistent
                        else ("Requires Verification", f"one-off signal near {f['kind']} of unknown heat use"))
        elif persistent:
            cat, why = ("Persistent Non-Industrial Thermal Source",
                        "recurring heat with no mapped facility, such as an unmapped kiln, landfill or coal-seam fire")
        elif agri and e["maxFrp"] < 15:
            cat, why = "Likely Agricultural Burning", f"{MONTHS[month]} is crop-residue burning season in {state}"
        elif all_low and day_only and e["detections"] == 1 and e["maxFrp"] < 2:
            cat, why = "Sun Glint / False Positive", "single low-confidence daytime pixel with very low heat"
        else:
            cat, why = "Requires Verification", "isolated detection the open data can't explain"

        # ── reasons, in reading order ──
        rs: list[str] = []
        where = f"Inside {state}, India"
        if r.get("place_name"):
            dist_txt = "at" if r["place_km"] < 1 else f"{r['place_km']:.0f} km {r['place_dir']} of"
            where += f", {dist_txt} {r['place_name']}"
            if r.get("district"):
                where += f" ({r['district']} district)"
        rs.append(where + ".")
        if f:
            rs.append(f"{f['km']:.1f} km from {f['name'] or 'an unnamed site'}, a {_facility_label(f)} "
                      f"[{_source_label(f)}].")
        elif nearest_any[i]:
            n = nearest_any[i]
            rs.append(f"No known heat source within {FACILITY_RADIUS_KM:.0f} km; nearest mapped site is "
                      f"{n['name'] or 'an unnamed ' + n['kind']} ({n['kind']}), {n['km']:.1f} km away.")
        else:
            rs.append(f"No known industrial facility within {MENTION_RADIUS_KM:.0f} km "
                      "(OpenStreetMap, WRI power-plant database).")
        seen = f"Seen on {e['days']} of the last {window} days ({e['detections']} detection{'s' * (e['detections'] != 1)}"
        if e["satellites"]:
            seen += f"; {', '.join(e['satellites'])}"
        seen += ")"
        if e["firstSeen"]:
            seen += f", {e['firstSeen']} to {e['lastSeen']}" if e["firstSeen"] != e["lastSeen"] else f", on {e['lastSeen']}"
        rs.append(seen + ".")
        if e["maxFrp"] >= config.FRP_HIGH_MIN:
            rs.append(f"Peak fire radiative power {e['maxFrp']} MW, above the {config.FRP_HIGH_MIN:.0f} MW high-heat threshold.")
        else:
            rs.append(f"Peak fire radiative power {e['maxFrp']} MW, a small or partial-pixel heat source.")
        rs.append(f"Detected at night on {e['nightPasses']} pass{'es' * (e['nightPasses'] != 1)}, which rules out sun glint."
                  if not day_only else "Daytime detections only, so sun glint or hot surfaces cannot be ruled out.")
        if all_low:
            rs.append("FIRMS rated every detection low-confidence.")
        elif e["lowConfidenceShare"] > 0:
            rs.append(f"FIRMS confidence mixed ({e['lowConfidenceShare']:.0%} of detections low).")
        if not f and not agri:
            rs.append(f"{MONTHS[month]} is outside this state's crop-residue burning season.")
        rs.append(f"Classified “{cat}”: {why}.")
        # Corroborated = backed by something beyond one pixel on one pass: a
        # repeat detection, another day, or a mapped facility.
        corroborated = (e["detections"] >= 2 or e["days"] >= 2 or f is not None) and (
            cat != "Sun Glint / False Positive"
        )
        if not corroborated:
            rs.append("Unconfirmed: a single detection with no repeat pass and no mapped facility yet.")

        corroborated_col.append(corroborated)
        cats.append(cat)
        reasons_col.append(rs)
        evidence_col.append(e)
        facility_col.append(None if not f else {
            "name": f["name"], "kind": f["kind"], "detail": f["detail"], "operator": f.get("operator") or "",
            "capacityMw": _capacity(f), "distanceKm": round(f["km"], 2), "source": f["source"],
            "ref": f["ref"], "url": f["url"],
        })

    ev["category"] = cats
    ev["corroborated"] = corroborated_col
    ev["reasons"] = reasons_col
    ev["evidence"] = evidence_col
    ev["facility"] = facility_col
    return ev


def _sat_name(code: str) -> str:
    """FIRMS VIIRS codes: "N" = Suomi NPP, "N20" = NOAA-20, "N21" = NOAA-21."""
    c = code.upper()
    if "N21" in c or "NOAA-21" in c or "NOAA21" in c:
        return "NOAA-21"
    if "N20" in c or "NOAA-20" in c or "NOAA20" in c or c == "J1":
        return "NOAA-20"
    if "AQUA" in c or c == "A":
        return "Aqua"
    if "TERRA" in c or c == "T":
        return "Terra"
    return "S-NPP"


def facilities_geojson() -> dict:
    """Compact facility layer for the globe (name, kind, source link)."""
    fac = _facilities()
    return {
        "type": "FeatureCollection",
        "attribution": "© OpenStreetMap contributors (ODbL); WRI Global Power Plant Database (CC BY 4.0)",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
                "properties": {"name": r["name"], "kind": r["kind"], "source": r["source"], "url": r["url"],
                               "capacityMw": r["capacity_mw"] if pd.notna(r["capacity_mw"]) else None},
            }
            for r in fac.to_dict("records")
        ],
    }
