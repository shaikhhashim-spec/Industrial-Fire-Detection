"""Offline global proximity context. Proximity never establishes fire cause or borders."""
from __future__ import annotations

from pathlib import Path
import io
import zipfile

import numpy as np
import pandas as pd
import requests
from sklearn.neighbors import BallTree

import config
from src.firms.fetch import _atomic_cache_text

WRI_URL = "https://raw.githubusercontent.com/wri/global-power-plant-database/master/output_database/global_power_plant_database.csv"
GEONAMES_URL = "https://download.geonames.org/export/dump/cities15000.zip"
THERMAL_FUELS = {"Coal", "Gas", "Oil", "Petcoke", "Biomass", "Waste", "Cogeneration", "Nuclear"}
EARTH_KM = 6371.0088


def refresh_wri_reference(path: Path | None = None) -> None:
    """Explicit, bounded reference download; never done per event or page load."""
    path = path or config.GLOBAL_WRI_PATH
    with requests.get(WRI_URL, stream=True, timeout=(10, 60)) as response:
        response.raise_for_status()
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > 16 * 1024 * 1024:
                raise ValueError("WRI reference exceeds 16 MiB limit")
            chunks.append(chunk)
    text = b"".join(chunks).decode("utf-8-sig")
    columns = pd.read_csv(io.StringIO(text), nrows=0).columns
    if not {"latitude", "longitude", "name", "primary_fuel", "gppd_idnr"}.issubset(columns):
        raise ValueError("WRI reference lacks required columns")
    _atomic_cache_text(path, text)


def _parse_places(text: str) -> pd.DataFrame:
    raw = pd.read_csv(io.StringIO(text), sep="\t", header=None, keep_default_na=False)
    if len(raw.columns) != 19:
        raise ValueError("GeoNames cities table must have 19 columns")
    places = raw.rename(columns={1: "name", 4: "latitude", 5: "longitude", 8: "countryCode", 14: "population"})
    places = _valid_points(places)
    return places[pd.to_numeric(places.population, errors="coerce") > 15000].reset_index(drop=True)


def refresh_geonames_reference(path: Path | None = None) -> None:
    """Read the expected ZIP member only; bound download and decompression."""
    path = path or config.GLOBAL_PLACES_PATH
    with requests.get(GEONAMES_URL, stream=True, timeout=(10, 60)) as response:
        response.raise_for_status()
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > 8 * 1024 * 1024:
                raise ValueError("GeoNames ZIP exceeds 8 MiB download limit")
            chunks.append(chunk)
    with zipfile.ZipFile(io.BytesIO(b"".join(chunks))) as archive:
        names = archive.namelist()
        if names.count("cities15000.txt") != 1 or any(name not in {"cities15000.txt", "readme.txt"} for name in names):
            raise ValueError("Unexpected GeoNames ZIP members")
        member = archive.getinfo("cities15000.txt")
        if member.file_size > 32 * 1024 * 1024 or member.flag_bits & 1 or member.is_dir():
            raise ValueError("Unsafe GeoNames ZIP member")
        with archive.open(member) as file:
            body = file.read(32 * 1024 * 1024 + 1)
        if len(body) > 32 * 1024 * 1024:
            raise ValueError("GeoNames table exceeds decompression limit")
    text = body.decode("utf-8-sig")
    if _parse_places(text).empty:
        raise ValueError("GeoNames table contains no valid populated cities")
    _atomic_cache_text(path, text)


def _valid_points(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    for column in ("latitude", "longitude"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame[frame.latitude.between(-90, 90) & frame.longitude.between(-180, 180)].reset_index(drop=True)


def load_references() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    facilities, places = pd.DataFrame(), pd.DataFrame()
    status = {"facilities": "unavailable", "places": "unavailable", "countryAttribution": "unavailable: no global boundary polygons"}
    if config.GLOBAL_WRI_PATH.exists():
        try:
            facilities = _valid_points(pd.read_csv(config.GLOBAL_WRI_PATH, keep_default_na=False))
            if not {"name", "primary_fuel", "gppd_idnr"}.issubset(facilities.columns):
                raise ValueError("WRI reference lacks facility identity columns")
            facilities = facilities[facilities.primary_fuel.isin(THERMAL_FUELS)].reset_index(drop=True)
            status["facilities"] = f"WRI static reference: {len(facilities)} thermal plants; proximity only"
        except (ValueError, KeyError, OSError, pd.errors.ParserError):
            facilities = pd.DataFrame()
            status["facilities"] = "unavailable: invalid WRI reference"
    if config.GLOBAL_PLACES_PATH.exists():
        try:
            places = _parse_places(config.GLOBAL_PLACES_PATH.read_text(encoding="utf-8"))
            status["places"] = f"GeoNames cities15000: {len(places)} cities; nearest place is not a border lookup"
        except (ValueError, KeyError, AttributeError, OSError, pd.errors.ParserError):
            places = pd.DataFrame()
            status["places"] = "unavailable: invalid GeoNames reference"
    return facilities, places, status


def _nearest(events: list[dict], reference: pd.DataFrame):
    tree = BallTree(np.radians(reference[["latitude", "longitude"]].to_numpy(dtype=float)), metric="haversine")
    distance, index = tree.query(np.radians([[e["latitude"], e["longitude"]] for e in events]), k=1)
    return zip(distance[:, 0] * EARTH_KM, index[:, 0])


def enrich_context(events: list[dict], facilities: pd.DataFrame, places: pd.DataFrame) -> None:
    if not events:
        return
    if not facilities.empty:
        for event, (distance, index) in zip(events, _nearest(events, facilities)):
            if distance > 3:
                continue
            row = facilities.iloc[index]
            capacity = pd.to_numeric(row.get("capacity_mw"), errors="coerce")
            event["facility"] = {
                "name": str(row["name"]), "kind": "thermal power plant",
                "detail": str(row["primary_fuel"]), "operator": str(row.get("owner", "")),
                "capacityMw": float(capacity) if pd.notna(capacity) and np.isfinite(capacity) else None,
                "distanceKm": round(float(distance), 2), "source": "WRI Global Power Plant Database (CC BY 4.0)",
                "ref": str(row["gppd_idnr"]), "url": "https://github.com/wri/global-power-plant-database",
            }
            event["reasons"].append(f"Mapped WRI thermal plant {distance:.2f} km away; proximity does not prove an industrial fire.")
    if not places.empty:
        for event, (distance, index) in zip(events, _nearest(events, places)):
            if distance > 100:
                continue
            row = places.iloc[index]
            event["place"] = {"name": str(row["name"]), "distanceKm": round(float(distance), 1), "direction": ""}
            event["reasons"].append("Nearest GeoNames city is proximity context; country and district are unverified.")


def facilities_geojson(facilities: pd.DataFrame) -> dict:
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [float(r.longitude), float(r.latitude)]},
         "properties": {"name": str(r["name"]), "kind": "thermal power plant", "detail": str(r.primary_fuel),
                        "ref": str(r.gppd_idnr), "source": "WRI Global Power Plant Database (CC BY 4.0)"}}
        for _, r in facilities.iterrows()
    ]}
