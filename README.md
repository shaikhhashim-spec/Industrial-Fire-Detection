# SIH26162 — AI-Based Detection & Classification of Industrial Fires and Persistent Thermal Sources

Classifies NASA satellite thermal hotspots in the Jharkhand–Odisha Iron Ore & Steel Belt
(Jamshedpur, Rourkela, Keonjhar, Sundargarh, West Singhbhum, Jharia) as industrial fires,
persistent non-industrial thermal sources (e.g. coal-seam fires), flares, agricultural
burning, or noise — using only free public data (NASA FIRMS + OpenStreetMap).

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

Get a free FIRMS API key at https://firms.modaps.eosdis.nasa.gov/api/map_key/, then:

```bash
copy .env.example .env
# edit .env and paste: FIRMS_MAP_KEY=your_key_here
```

Without a key, the pipeline automatically runs on synthetic sample data (`src/sample_data.py`)
so the app still works end-to-end for development/demo purposes.

## Run

```bash
streamlit run app.py
```

Click **Run / Refresh Pipeline** in the sidebar. This fetches (or generates sample) hotspots,
pulls OSM industrial/mining zones, computes persistence, applies rule-based scoring, trains a
Random Forest validation layer, and renders everything on the filterable map.

You can also run the pipeline standalone (writes `output/classified_hotspots.{geojson,csv}`):

```bash
python -m src.pipeline
```

## Pipeline

1. **`src/fetch_firms.py`** — pulls FIRMS hotspots (VIIRS/MODIS) for the bounding box over a
   rolling 60-day window, in 10-day API chunks.
2. **`src/persistence.py`** — snaps hotspots to a ~1km grid, counts distinct detection days per
   cell; ≥5 days ⇒ "persistent".
3. **`src/osm_industrial.py`** — Overpass query for `landuse=industrial`, quarries, mines,
   `man_made=works` in the bbox. Falls back live → cache → synthetic zones if Overpass is down.
4. **`src/zone_join.py`** — spatial join of hotspots against buffered (500m) industrial polygons.
5. **`src/scoring.py`** — rule-based v1 classifier combining confidence, FRP, persistence, and
   zone type into a label.
6. **`src/ml_model.py`** — Random Forest v2 layer trained on the v1 labels; reports accuracy and
   feature importance as a validation/explainability layer.
7. **`src/pipeline.py`** — orchestrates the above and writes GeoJSON/CSV output for the dashboard.
8. **`app.py`** — Streamlit + Folium dashboard: filterable map, legend, summary stats, ML
   diagnostics.

## Region

Bounding box: 21.0°N–23.9°N, 83.5°E–87.0°E (extended slightly north of the original
21.0–23.5°N brief to include the Jharia coalfield, whose decades-long underground seam fires
are the headline "persistent thermal source" story for the pitch). Adjust in `config.py`.

## Fallback behavior (per the risk plan)

- No FIRMS key / API down → synthetic sample data (`src/sample_data.py`), clearly labeled in the UI.
- Overpass down / rate-limited → cached OSM pull from a previous run, else synthetic industrial zones.
- Not enough labeled data to train the ML layer → `ml_label` falls back to `rule_label`.
