"""Central configuration for the thermal-source detection pipeline."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
OUTPUT_DIR = BASE_DIR / "output"

for d in (DATA_DIR, RAW_DIR, OUTPUT_DIR):
    d.mkdir(parents=True, exist_ok=True)

# --- Target region: Jharkhand-Odisha Iron Ore & Steel Belt -----------------
# Extended slightly north (23.5 -> 23.9) from the original brief so the
# bounding box also covers the Jharia coalfield (~23.75N, 86.41E), which is
# the headline "persistent thermal source" story for the pitch narrative.
BBOX = {
    "min_lat": 21.0,
    "max_lat": 23.9,
    "min_lon": 83.5,
    "max_lon": 87.0,
}
# FIRMS area API wants "west,south,east,north"
FIRMS_AREA_STR = f"{BBOX['min_lon']},{BBOX['min_lat']},{BBOX['max_lon']},{BBOX['max_lat']}"
# Overpass wants "south,west,north,east"
OVERPASS_BBOX_STR = f"{BBOX['min_lat']},{BBOX['min_lon']},{BBOX['max_lat']},{BBOX['max_lon']}"

# --- FIRMS ------------------------------------------------------------------
FIRMS_MAP_KEY = os.getenv("FIRMS_MAP_KEY", "").strip()
FIRMS_SOURCES = ["VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "MODIS_NRT"]
FIRMS_TOTAL_DAYS = 60      # how far back to pull history
FIRMS_CHUNK_DAYS = 10      # max day_range per single FIRMS area API request
FIRMS_BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
FIRMS_STATUS_URL = "https://firms.modaps.eosdis.nasa.gov/mapserver/mapkey_status/"

# --- Overpass (OSM) -----------------------------------------------------
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_TIMEOUT = 90

# --- Persistence logic ----------------------------------------------------
GRID_SIZE_DEG = 0.01              # ~1.1 km grid cell at this latitude
PERSISTENCE_WINDOW_DAYS = 30      # rolling window used for the "persistent" rule
PERSISTENCE_MIN_DAYS = 5          # >= this many distinct days in the window => persistent

# --- Zone join --------------------------------------------------------------
INDUSTRIAL_BUFFER_M = 500         # buffer around industrial polygons, in metres
UTM_CRS = "EPSG:32645"            # UTM zone 45N, covers this bounding box

# --- Rule-based scoring thresholds ------------------------------------------
FRP_INDUSTRIAL_MIN = 10.0         # MW, "notable" heat output
FRP_HIGH_MIN = 25.0               # MW, strong fire signal
AGRI_BURN_MONTHS = {10, 11, 12, 1, 2, 3}  # crop-residue burning season (post-harvest)

RULE_LABELS = [
    "Industrial Fire",
    "Persistent Non-Industrial Thermal Source",
    "Industrial Flare / Transient Activity",
    "Likely Agricultural Burning",
    "Likely Noise / Sun Glint",
    "Unclassified / Needs Review",
]

CLASSIFIED_GEOJSON = OUTPUT_DIR / "classified_hotspots.geojson"
CLASSIFIED_CSV = OUTPUT_DIR / "classified_hotspots.csv"
MODEL_PATH = OUTPUT_DIR / "model.joblib"
OSM_CACHE_PATH = DATA_DIR / "osm_industrial.geojson"
