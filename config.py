"""Central configuration for the thermal-source intelligence platform.

All thresholds here are PROTOTYPE/OPERATIONAL PARAMETERS tuned against the
real FIRMS data this project pulled for this region and window — not
scientifically established constants. See README.md "Scientific Honesty"
section before presenting any number from this file as ground truth.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
CACHE_DIR = DATA_DIR / "cache"
DEMO_DIR = DATA_DIR / "demo"
OUTPUT_DIR = BASE_DIR / "output"
MODELS_DIR = BASE_DIR / "models"

for d in (DATA_DIR, RAW_DIR, PROCESSED_DIR, CACHE_DIR, DEMO_DIR, OUTPUT_DIR, MODELS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# --- Target region: Jharkhand-Odisha Iron Ore & Steel Belt -----------------
# Extended slightly north (23.5 -> 23.9) from the original brief so the
# bounding box also covers the Jharia coalfield (~23.75N, 86.41E), which is
# the headline "persistent thermal source" story for the pitch narrative.
BBOX = {"min_lat": 21.0, "max_lat": 23.9, "min_lon": 83.5, "max_lon": 87.0}
REGION_NAME = "Jharkhand–Odisha Iron Ore & Steel Belt"
REGION_PLACES = ["Jamshedpur", "Rourkela", "Keonjhar", "Sundargarh", "West Singhbhum",
                  "Noamundi", "Barbil", "Joda", "Jharia"]

# FIRMS area API wants "west,south,east,north"
FIRMS_AREA_STR = f"{BBOX['min_lon']},{BBOX['min_lat']},{BBOX['max_lon']},{BBOX['max_lat']}"
# Overpass wants "south,west,north,east"
OVERPASS_BBOX_STR = f"{BBOX['min_lat']},{BBOX['min_lon']},{BBOX['max_lat']},{BBOX['max_lon']}"

# --- FIRMS -------------------------------------------------------------------
# FIRMS_API_KEY is the documented name; FIRMS_MAP_KEY is kept for backward
# compatibility with earlier setup. Never hard-code a key here.
FIRMS_API_KEY = (os.getenv("FIRMS_API_KEY") or os.getenv("FIRMS_MAP_KEY") or "").strip()
FIRMS_SOURCES = ["VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "MODIS_NRT"]
FIRMS_TOTAL_DAYS = 60      # how far back to pull history
FIRMS_CHUNK_DAYS = 5       # max day_range per single FIRMS area API request (this MAP_KEY tier caps it at 5, not the documented 10)
FIRMS_BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
FIRMS_STATUS_URL = "https://firms.modaps.eosdis.nasa.gov/mapserver/mapkey_status/"
FIRMS_CACHE_TTL_HOURS = 6.0
FIRMS_MAX_RETRIES = 4
FIRMS_BACKOFF_FACTOR = 1.5
FIRMS_COUNTRY_BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/country/csv"

# --- National (India-wide) mode ---------------------------------------------
# Deliberately shallow: "latest observations", not a 60-day history pull, per
# the platform's own staged-architecture requirement (don't repeatedly
# download a long window country-wide on every page load).
NATIONAL_COUNTRY_CODE = "IND"
# Mainland + island territories extent; used to tile area/csv requests when
# FIRMS's country/csv endpoint is unavailable (see src/firms/fetch.py).
INDIA_BBOX = {"min_lat": 6.0, "max_lat": 37.5, "min_lon": 68.0, "max_lon": 97.5}
NATIONAL_FIRMS_SOURCES = ["VIIRS_SNPP_NRT", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT"]
NATIONAL_DAY_RANGE = 2  # latest 24-48 hours pulled live on each run
NATIONAL_PERSISTENCE_MIN_DAYS = 2  # fallback threshold when no accumulated history exists yet (single fresh batch)
NATIONAL_DB_PATH = DATA_DIR / "national_hotspots.db"
# Each live run's fresh 2-day pull is merged into this persistent store
# (never touched in Demo Mode — same demo/live isolation guarantee as the
# regional store), so persistence is judged against real accumulated
# history rather than only ever the latest 48h snapshot.
NATIONAL_HISTORY_DAYS = 30
NATIONAL_PERSISTENCE_MIN_DAYS_HISTORY = 5  # >= this many distinct days in NATIONAL_HISTORY_DAYS => persistent, once real history exists
INDIA_STATES_PATH = BASE_DIR / "data" / "reference" / "india_states.geojson"
# The published dataset (GADM-derived) uses these older names; keep the
# state polygons' real geometry untouched and just re-label for matching
# against this project's own current-name usage.
STATE_NAME_ALIASES = {"Orissa": "Odisha", "Uttaranchal": "Uttarakhand"}
# National-scale risk uses only signals available without an OSM join
# (no industrial-proximity component) — a distinct, simpler model from the
# full regional RISK_WEIGHTS, not a stand-in for it.
NATIONAL_RISK_WEIGHTS = {"persistence": 0.40, "frp": 0.35, "confidence": 0.25}

# --- Region registry ----------------------------------------------------------
# Keeps the architecture region-independent — new regions can be added here
# without touching pipeline/app code, per the platform's national-scalability
# requirement.
SINGRAULI_REGION_NAME = "Singrauli Coal & Power Corridor"
SINGRAULI_BBOX = {"min_lat": 23.9, "max_lat": 24.6, "min_lon": 82.4, "max_lon": 83.3}

REGIONS = {
    "jharkhand_odisha": {
        "name": "Jharkhand–Odisha Iron Ore & Steel Belt",
        "detailed": True,   # full geospatial + AI pipeline
        "bbox": BBOX,
    },
    "india": {
        "name": "India",
        "detailed": False,  # detection + spatial distribution only
        "bbox": INDIA_BBOX,
    },
    "singrauli": {
        "name": SINGRAULI_REGION_NAME,
        "bbox": SINGRAULI_BBOX,
        "detailed": False,
    },
}
DEFAULT_REGION = "india"

# --- Overpass (OSM) -----------------------------------------------------
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_TIMEOUT = 90
OVERPASS_CACHE_TTL_HOURS = 24.0

# --- Grid + persistence engine ----------------------------------------------
GRID_SIZE_DEG = 0.01              # ~1.1 km grid cell at this latitude
PERSISTENCE_WINDOWS_DAYS = [7, 30, 60]   # rolling windows reported alongside each other
PERSISTENCE_DEFAULT_WINDOW_DAYS = 30     # which window the "is_persistent" flag uses
PERSISTENCE_MIN_DAYS = 5                 # >= this many distinct days in the window => persistent
                                          # (configurable from the UI's Settings panel at runtime)

# --- Hotspot status thresholds ----------------------------------------------
STATUS_NEW_WITHIN_DAYS = 3        # first-ever detection younger than this => NEW
STATUS_INACTIVE_AFTER_DAYS = 14   # no detection in this long => RESOLVED/INACTIVE

# --- Geospatial join ----------------------------------------------------------
INDUSTRIAL_BUFFER_M = 500         # "inside an industrial zone" buffer, in metres
UTM_CRS = "EPSG:32645"            # UTM zone 45N, covers this bounding box

# --- Rule-based scoring thresholds ------------------------------------------
# Calibrated against real VIIRS/MODIS FRP for this region+window (not a
# fictional textbook range): p50=1.7MW, p90=5.2MW, p95=6.8MW, p99=10.5MW,
# max=19.4MW observed. These are prototype operating parameters, not a
# scientifically validated fire-detection standard.
FRP_INDUSTRIAL_MIN = 3.0          # MW, "notable" heat output (~80th pctile of observed data)
FRP_HIGH_MIN = 8.0                # MW, strong fire signal (~95th pctile)
CONF_INDUSTRIAL_FIRE_MIN = 60.0   # 0-100 normalized confidence
CONF_FLARE_MIN = 50.0
AGRI_BURN_MONTHS = {10, 11, 12, 1, 2, 3}  # crop-residue burning season (post-harvest)
FOREST_NEAR_KM = 1.0   # "near/within a mapped forest" evidence threshold for wildfire classification
WATER_NEAR_KM = 0.5    # "near/within a mapped water body" — sun-glint is a well-documented FIRMS false-positive cause here

# Category set reconciles the spec's requested taxonomy with categories this
# project's own calibration against real data required (see
# "Persistent Non-Industrial Thermal Source" and "Persistent Industrial
# Activity" split below — an uncalibrated FRP bar left 81% of real
# detections unclassifiable; see README "AI Methodology").
RULE_LABELS = [
    "Likely Industrial Fire",
    "Persistent Industrial Activity",
    "Persistent Non-Industrial Thermal Source",
    "Transient Industrial Flare",
    "Likely Agricultural Burning",
    "Likely Wildfire",
    "Sun Glint / False Positive",
    "Requires Verification",
]

# --- Risk score (0-100) ------------------------------------------------------
# "Prototype Operational Risk Score" — NOT an official government fire-risk
# standard. Weights are configurable from the dashboard's Settings panel.
RISK_WEIGHTS = {
    "persistence": 0.30,
    "frp": 0.25,
    "confidence": 0.20,
    "industrial_proximity": 0.15,
    "recurrence": 0.10,
}
RISK_LEVELS = [
    (0, 25, "LOW"),
    (26, 50, "MODERATE"),
    (51, 75, "HIGH"),
    (76, 100, "CRITICAL"),
]

# --- Alert engine & Critical Dispatch -----------------------------------------
ALERT_CRITICAL_RISK_MIN = 76
ALERT_HIGH_RISK_MIN = 51
ALERT_FRP_SPIKE_MULTIPLIER = 2.0   # current FRP vs cell's own historical average

# --- Wind / plume overlay -----------------------------------------------------
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
WIND_CACHE_TTL_HOURS = 6.0
WIND_FALLBACK_SPEED_KMH = 12.0
WIND_FALLBACK_DIRECTION_DEG = 180.0  # meteorological "wind from" direction

# --- Alert & Messaging Dispatch Parameters ------------------------------------
ALERT_RECIPIENT_PHONE = os.getenv("ALERT_RECIPIENT_PHONE", "9967541336")
ALERT_AUTO_DISPATCH_CRITICAL = os.getenv("ALERT_AUTO_DISPATCH_CRITICAL", "true").lower() in ("1", "true", "yes")
TWILIO_ACCOUNT_SID = (os.getenv("TWILIO_ACCOUNT_SID") or "").strip()
TWILIO_AUTH_TOKEN = (os.getenv("TWILIO_AUTH_TOKEN") or "").strip()
TWILIO_FROM_NUMBER = (os.getenv("TWILIO_FROM_NUMBER") or "").strip()
ALERT_SMS_TO_NUMBER = (os.getenv("ALERT_SMS_TO_NUMBER") or ALERT_RECIPIENT_PHONE).strip()
ALERT_WEBHOOK_URL = (os.getenv("ALERT_WEBHOOK_URL") or "").strip()
TELEGRAM_BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()

# --- Output / model paths -----------------------------------------------------
CLASSIFIED_GEOJSON = OUTPUT_DIR / "classified_hotspots.geojson"
CLASSIFIED_CSV = OUTPUT_DIR / "classified_hotspots.csv"
MODEL_PATH = MODELS_DIR / "classifier.pkl"
OSM_CACHE_PATH = CACHE_DIR / "osm_industrial.geojson"
LANDCOVER_CACHE_PATH = CACHE_DIR / "osm_landcover.geojson"
DEMO_DATASET_PATH = DEMO_DIR / "demo_hotspots.csv"
DB_PATH = DATA_DIR / "hotspots.db"
ALERT_LOG_PATH = PROCESSED_DIR / "critical_alerts_log.json"


