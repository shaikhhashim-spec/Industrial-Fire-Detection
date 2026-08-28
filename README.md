# Thermal Intelligence — SIH26162

**AI-Based Detection & Classification of Industrial Fires and Persistent Thermal Sources**
Ministry: NTRO · Category: Software · Target: Jharkhand–Odisha Iron Ore & Steel Belt

> This is an **AI-assisted early-warning and prioritization platform**, not an
> autonomous system that confirms fires. Satellite detection is not ground
> truth — every classification is labeled with its confidence, every risk
> score is a *prototype operational* score, and ambiguous detections are
> explicitly marked **Requires Verification** rather than forced into a
> confident-sounding category. See [Scientific Honesty](#scientific-honesty).

---

## 1. Problem Statement

NASA satellites detect thermal "hotspots" globally, but a raw hotspot feed
can't tell a real industrial fire apart from a gas flare, sun glint, or
routine agricultural burning. Jharkhand–Odisha's steel and mining belt has a
genuine, decades-long example of exactly this ambiguity: the Jharia coalfield
underground seam fires, still burning since the 1970s. This project builds a
pipeline that pulls satellite hotspot data for the region, tracks which
hotspots keep recurring over time, cross-references them against real
industrial/mining zone maps, scores and classifies each one, and surfaces the
result on a live, filterable command-center dashboard — built entirely on
free public data.

## 2. Solution

```
NASA FIRMS  ──┐
              ├─▶ Clean ─▶ Persistence Engine ─▶ OSM Geospatial Join ─▶ Feature
OpenStreetMap ┘                                                        Engineering
                                                                            │
                                                                            ▼
                                                    Rule-Based Classifier (explainable)
                                                                            │
                                                                            ▼
                                          ML Validation Layer (Random Forest, weak labels)
                                                                            │
                                                                            ▼
                                                    Risk Scoring (0-100, weighted)
                                                                            │
                                                                            ▼
                                        Status Assignment + Alert Engine + SQLite Store
                                                                            │
                                                                            ▼
                                              Streamlit Command-Center Dashboard
```

Every stage is a standalone, testable module — see [Architecture](#architecture).

## 3. Data Sources

| Source | What | Key needed? |
|---|---|---|
| [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/api/) | Thermal hotspots: lat/lon, brightness, FRP, confidence, date/time, satellite | Yes (free) |
| [OpenStreetMap](https://overpass-api.de/) (via Overpass) | Industrial land, quarries/mines, power plants — used for zone context + proximity | No |
| OpenStreetMap (via Overpass, separate query) | Forest, water bodies, farmland/orchard — used for wildfire/agri-burn/sun-glint evidence | No |

Every hotspot/event carries `zone_type` (binary "industrial"/"other" — the
value the rule engine, ML features, and risk score actually key off of, kept
stable) plus, purely as additional evidence/context, `zone_kind` ("mine" /
"power" / "industrial" / "other") and three separate distances:
`industrial_distance_km` (nearest industrial/mining/power feature of any
kind), `mine_distance_km` (nearest quarry/mineshaft), and
`power_distance_km` (nearest power plant). **A real bug was found and fixed
while adding the mine/power split**: `osm2geojson` nests each OSM feature's
tags under a single `tags` dict column rather than flattening them to
top-level columns, and the zone-kind classifier's tag reader explicitly
skipped any dict-valued column — meaning it had *never* actually seen a
`landuse=quarry`, `man_made=mineshaft`, or `power=plant` tag, and every zone
silently fell through to "industrial". `mine_distance_km` (and the ML
model's `mine_zone_flag` feature) had therefore been `NaN`/always-zero for
the life of the project. Fixed by reading the nested `tags` dict as well as
any flat columns; re-verified against the real ~2,100-zone cached Overpass
pull for this region, which is genuinely 1,167 mine / 902 industrial / 63
power features once correctly classified.

## 4. AI Methodology

**Two layers, deliberately kept separate:**

1. **Rule-based classifier (v1)** — explainable by construction. Combines
   confidence, FRP, persistence, and industrial-zone proximity into one of 8
   categories, each with a plain-language reason and an evidence list (see
   `src/ml/rules.py`). This is the platform's primary, trustworthy signal.
2. **ML validation layer (v2)** — a Random Forest trained on the rule
   engine's own output ("weak labels," not human-verified ground truth). It
   exists to sanity-check the rule engine (agreement rate, feature
   importance) — **not** to replace it. See [Model Evaluation](#model-evaluation-caveat).

**Categories:** Likely Industrial Fire · Persistent Industrial Activity ·
Persistent Non-Industrial Thermal Source · Transient Industrial Flare ·
Likely Agricultural Burning · Likely Wildfire · Sun Glint / False Positive ·
Requires Verification.

**A real calibration finding worth knowing:** the first version of the FRP
threshold ("what counts as a notable fire") was set at 10 MW, based on
plausible-sounding textbook numbers. Against real live FIRMS data for this
region, that threshold sat *above the 99th percentile* of actual detections
— 81% of everything real the pipeline saw landed in "Unclassified." Recalibrating
against the real observed distribution (p50=1.7MW, p90=5.2MW, p99=10.5MW,
max=19.4MW) and adding two categories the rule engine was genuinely missing
(`Persistent Industrial Activity` for low-intensity-but-recurring industrial
heat, and `Likely Wildfire` for non-industrial one-off detections outside
burn season) dropped that to under 1%. All thresholds live in `config.py`,
clearly commented as prototype/operational parameters, not scientific constants.

## 5. Persistence Methodology

Every detection is snapped to a **~1km grid cell** (`src/geospatial/grid.py`).
For each cell, the platform tracks:

- Distinct active days across **7-day, 30-day, and 60-day** rolling windows
- Total detection count, average/maximum FRP, first/last detection date
- Recurrence frequency (detections per day since first seen)

Default rule: **≥5 distinct active days in the 30-day window ⇒ persistent**
(configurable in `config.PERSISTENCE_MIN_DAYS`, exposed in the dashboard's
Settings panel). Persistence tracking is extended across pipeline runs via
the local SQLite store — a detection FIRMS's live feed no longer serves
still counts toward a cell's total, capped back to the same 60-day span a
single fetch would cover so the window doesn't silently grow.

## 6. Risk Scoring

A **Prototype Operational Risk Score** (0–100) — explicitly *not* an
official government fire-risk standard. Five independently-normalized
components, weighted (`config.RISK_WEIGHTS`, configurable):

| Component | Weight |
|---|---|
| Persistence | 30% |
| FRP | 25% |
| Satellite Confidence | 20% |
| Industrial Proximity | 15% |
| Recent Recurrence | 10% |

Risk levels: **0–25 LOW · 26–50 MODERATE · 51–75 HIGH · 76–100 CRITICAL.**

## 7. Hotspot Status Lifecycle

Every grid cell carries one status: **NEW** (first seen recently) →
**RECURRING** (multiple detections, below the persistence bar) →
**PERSISTENT** (crossed the persistence bar) → **HIGH RISK** / **CRITICAL**
(risk score crosses 51 / 76, overriding the lifecycle label) →
**RESOLVED/INACTIVE** (no detection in 14+ days). See `src/utils/status.py`.

## 8. Model Evaluation Caveat

**Every accuracy/precision/recall/F1/confusion-matrix number shown in the
dashboard is computed on a held-out split — never fabricated — but it is
scored against rule-derived ("weak") labels, not a human-verified
ground-truth dataset.** It measures how well the Random Forest reproduces
the rule engine, not confirmed real-world classification accuracy. A ~97–100%
score is expected and correct to see, and should be explained as such, not
presented as "the AI is 97% accurate at detecting real fires." Production
deployment would need a manually validated dataset. This caveat is displayed
alongside the metrics on the dashboard's AI Model page, not just here.

## 9. Installation

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows (use source .venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
```

### Getting a FIRMS API key

1. Register (free, ~2 minutes): https://firms.modaps.eosdis.nasa.gov/api/map_key/
2. Copy `.env.example` to `.env` and paste your key in as `FIRMS_API_KEY`.
3. **Note:** some key tiers cap `day_range` at 5 instead of the documented
   10 — `config.FIRMS_CHUNK_DAYS` is already set to 5 to be safe; if your key
   supports 10, you can raise it for fewer, larger requests.

Without a key, or with **Demo Mode** switched on (sidebar bottom, or the
Settings page), the app runs entirely on a fixed local demo dataset — no
network, no key, ever required.

## 10. Running the Application

```bash
streamlit run app.py
```

Opens at `http://localhost:8501`. The left sidebar is pure navigation —
**Overview, Live Map, Events, Alerts, Analytics, Investigations, Validation,
AI Model, Data, Settings** — plus Demo Mode at the bottom. The top bar holds
the **Region** switch (India ↔ Jharkhand–Odisha Belt), live data-source
status, global search, and the alert count. Pipeline runs, the FIRMS key,
Analyst Mode, Presentation Mode, and prototype thresholds all live on the
**Settings** page (per-region). Filters live at the top of whichever page
uses them (Live Map, Events, Analytics, Investigations) and drive the map,
KPIs, charts, and tables together from the same filtered dataset.

## 11. How Demo Mode Works

Demo Mode uses a **fixed, deterministic dataset** written once to
`data/demo/demo_hotspots.csv` (regenerate by deleting that file). It is
**fully isolated from the live SQLite store** — running Demo Mode never
reads from or writes to `data/hotspots.db`, so synthetic and real detections
can never contaminate each other's persistence calculations. Demo Mode
covers 7 of the 8 classification categories out of the box; `Likely
Agricultural Burning` only appears if at least one of the last 60 days
falls in the Oct–Mar burn season — during monsoon months it correctly does
not appear, matching what real live data showed too, rather than faking a
date that would just get filtered out by the pipeline's own window logic.

## 12. Fallback Hierarchy

```
LIVE API  →  LOCAL CACHE  →  DEMO DATASET
```

FIRMS auth errors, network timeouts, empty responses, and Overpass downtime
are all caught explicitly (`src/firms/fetch.py`, `src/geospatial/osm.py`) and
fall through this chain — the dashboard has never shown a blank page in
testing, including a live 504 from the public Overpass server during
development (it fell back to a local cache automatically).

## 13. Training / Updating the Model

The Random Forest retrains automatically on every pipeline run (`src/ml/train.py`),
saved to `models/classifier.pkl`. There is no separate manual training step —
each run's rule labels become that run's training data.

## 14. Architecture

```
project/
├── app.py                    # Streamlit command-center dashboard
├── config.py                 # Region, thresholds, weights — all in one place
├── requirements.txt
├── .env.example
├── conftest.py
│
├── data/
│   ├── raw/                  # Raw FIRMS pulls (one CSV per fetch day)
│   ├── processed/            # cluster_summary.csv, alerts.json (latest run)
│   ├── cache/                # FIRMS + OSM TTL cache
│   ├── demo/                 # Fixed demo dataset
│   └── reference/            # India states boundary (real GADM-derived dataset)
│
├── src/
│   ├── firms/fetch.py            # NASA FIRMS: retries, caching, error detection, area tiling
│   ├── geospatial/
│   │   ├── osm.py                # Overpass query + cache/fallback
│   │   ├── spatial_join.py       # Zone tagging + industrial/mine distance
│   │   └── grid.py               # ~1km grid assignment
│   ├── processing/
│   │   ├── cleaning.py           # Validation, dedup, region-bbox filtering
│   │   └── persistence.py        # 7/30/60-day persistence engine
│   ├── ml/
│   │   ├── features.py           # Feature engineering + normalization
│   │   ├── rules.py               # Explainable rule-based classifier
│   │   ├── train.py               # Random Forest training
│   │   ├── predict.py             # Inference
│   │   └── evaluation.py          # Metrics + confusion matrix + caveat
│   ├── risk/scoring.py           # 0-100 weighted risk score
│   ├── alerts/engine.py          # Alert generation
│   ├── utils/status.py           # NEW/RECURRING/PERSISTENT/HIGH RISK/CRITICAL
│   ├── national/
│   │   ├── states.py             # Real India state boundaries + point-in-polygon tagging
│   │   └── pipeline.py           # Lightweight national fetch→clean→grid→state→risk-lite
│   ├── classify.py               # Orchestrates persistence→features→rules→ML→risk→status
│   ├── pipeline.py               # Top-level (detailed region): fetch→clean→geo-join→classify→alerts
│   ├── store.py                  # SQLite persistent store
│   └── sample_data.py            # Demo dataset generators (regional + national)
│
├── models/classifier.pkl
├── JUDGE_QA.md                   # 20 honest Q&A on design decisions
└── tests/                        # pytest — 57 tests across 9 modules
```

`src/classify.py`'s `classify_hotspots(df)` is the platform's single most
important function: it expects a dataframe already carrying raw FIRMS
columns plus a `zone_type` from the geospatial join stage, and returns
`(detail_df, cluster_df, info)` — fully persistence-tracked, classified,
risk-scored, and status-assigned. Nothing about fetching or OSM is baked
into it, so it's independently testable and reusable if the fetch/geospatial
layers are ever swapped out.

## 15. Testing

```bash
pytest tests/ -v
```

41 tests across data cleaning, grid assignment, the persistence engine, risk
scoring, the rule classifier, the alert engine, and FIRMS fetch — including
edge cases: empty datasets, missing coordinates, missing FRP, invalid API
keys, network timeouts, duplicate detections, and malformed responses. All
FIRMS tests are mocked — no real key or network access needed to run them.

## 16. Deployment

The simplest path is [Streamlit Community Cloud](https://streamlit.io/cloud)
(free, GitHub login): push this repo, point it at `app.py`, and add
`FIRMS_API_KEY` as a secret in the app's settings (never commit `.env`).
Demo Mode means the deployed app is fully functional even before a key is
configured.

## 17. Implemented Features

- FIRMS fetch with retries, TTL caching, and error-payload detection
- Data cleaning with an auditable drop-report (not a silent shrink)
- ~1km grid persistence engine with 7/30/60-day windows
- OSM industrial/mining/power-plant geospatial join with distance calculation
- Explainable rule-based classifier (8 categories, evidence per detection)
- Random Forest validation layer with honest weak-label evaluation
- 0–100 configurable-weight risk score + 4-level risk classification
- NEW/RECURRING/PERSISTENT/HIGH RISK/CRITICAL/RESOLVED status lifecycle
- Alert engine (critical risk, persistent high-risk, FRP spikes, reactivation)
- SQLite persistent store with demo/live isolation
- Command-center dashboard, restructured around a fixed page-based
  information architecture rather than in-page tabs: a nav-only left
  sidebar (**Overview, Live Map, Events, Alerts, Analytics, Investigations,
  Validation, AI Model, Data, Settings**) and a top bar carrying the
  **Region** switch (India ↔ Jharkhand–Odisha Belt), live data-source
  status, global search (jump to a grid cell/state by ID), and the alert
  count. Same underlying pipeline output as before — KPIs, alert banner,
  clustered map (classification- or risk-colored, persistent-source halos),
  time-lapse playback, trend/distribution/confusion-matrix analytics,
  investigation panel with historical activity chart and incident report
  export, searchable/exportable Events table, system health panel, Analyst
  Mode — now organized as dedicated pages instead of tabs, with per-page
  filter panels instead of one shared sidebar filter stack
- A **Validation** page (belt only): a review queue over hotspots the rule
  engine marked `Requires Verification`, with Confirm/Reject/Needs
  Verification actions, persisted to a SQLite `analyst_reviews` audit-trail
  table (latest decision per event + timestamp), viewable on the Data page
- **Thermal anomaly detection** (`src/risk/anomaly.py`): per-grid-cell FRP
  baseline (mean/std over that cell's own prior detections) compared against
  its latest detection via z-score, deliberately simple by design (rolling
  mean/std, not e.g. Isolation Forest) and requiring ≥2 prior detections
  before attempting a verdict at all. Drives a dedicated `thermal_anomaly`
  alert type and a **"What Changed?"** section on the investigation panel
  (baseline FRP → latest FRP, % change, anomalous or not) — additive to,
  not a replacement for, the existing ratio-based `frp_spike` alert
- **Runtime-adjustable risk weights**: sliders on the Settings page let an
  analyst re-weight persistence/FRP/confidence/industrial-proximity/
  recurrence and click Recompute — re-scores already-loaded data (risk,
  status, alerts) without a full pipeline re-fetch/re-classification
- **Model versioning metadata**: each trained Random Forest is tagged with a
  version string and training timestamp, shown on the AI Model page
- **Cluster Analysis** (Analytics page): DBSCAN over event coordinates
  (haversine distance) groups nearby ~1km grid-cell events into candidate
  multi-cell sites — a spatial grouping heuristic, not a causal claim
- **Emerging Thermal Sources** (Analytics page): events not yet persistent
  but recently active with rising FRP relative to their own short history
- **HTML incident report** (alongside the existing plain-text export) — a
  styled, self-contained report a browser can print straight to PDF,
  without adding a PDF-generation dependency to the project
- Demo Mode fully isolated from live data
- National (India-wide) hotspot detection layer: real state boundary data,
  state-level filtering/aggregation, 6 map modes, top-states chart, staged
  architecture (no expensive national OSM join). Pages that require the full
  AI/geospatial pipeline (Investigations, Validation, AI Model) show an
  honest "switch to the belt" message in India mode rather than faking
  national-scale classification
- Presentation Mode (hides technical/admin pages for a clean 3-5 min demo)
- Methodology & Limitations disclaimer built into the dashboard
- Judge Q&A document (`JUDGE_QA.md`) — 20 honest, technical answers
- **Real OSM landcover context** (`src/geospatial/landcover.py`): a second,
  independently-cached Overpass query (forest/wood, water bodies, farmland/
  orchard) — deliberately kept separate from the industrial-zone query so
  that a failure fetching these (large landuse polygons over a multi-degree
  bbox are more likely to make Overpass time out) never breaks the
  already-reliable industrial join. Adds `forest_distance_km`,
  `water_distance_km`, `in_agricultural_zone` (real polygon-backed, not
  approximated) to every hotspot, used by the rule engine as genuine
  evidence: agricultural burning no longer relies on burn-season month
  alone, wildfire classification can now cite "within Xkm of mapped
  forest," and hotspots near mapped water bodies at low/moderate confidence
  are recognized as a likely sun-glint false positive (a well-documented
  FIRMS failure mode). When Overpass is unavailable for this query
  specifically, these fields are simply absent/False and the rule engine
  transparently falls back to its original burn-season-month approximation
  — never a crash, never fabricated context.
- 76-test pytest suite with edge-case coverage

## 18. Limitations & Future Improvements

Deliberately **not** implemented now, with the architecture left open to add them:

- ~~Forest/water/agricultural-zone booleans via real OSM polygons~~ — **now
  implemented** (`src/geospatial/landcover.py`), see section 17.
- **A true alert-history store / dismiss-state persistence** — alerts are
  recomputed fresh each run rather than diffed against a prior run's state
  (the analyst-review audit trail is persisted; the alert feed itself is not).
- **SHAP explanations** — evaluated and deliberately skipped: the rule
  engine's own per-detection evidence list plus the Random Forest's
  `feature_importances_` already give genuine, honest explainability without
  adding a new heavy ML dependency (`shap` is not installed) days before a
  demo. `src/ml/evaluation.py`'s feature-importance output is the intended
  substitute.
- **A true, generated PDF report** — the incident report now exports as
  both plain text and a styled, self-contained HTML file a browser can
  print straight to PDF (no external assets, works offline); a
  library-generated PDF (e.g. via `reportlab`) is a straightforward future
  addition once that dependency trade-off is acceptable.
- **Event/region side-by-side comparison view** — not built this pass;
  the underlying data (cluster_df, state_summary) already supports it.
- **Command palette (Ctrl+K), a persistent alert-history/dismiss-state
  store, role-based auth, i18n, Docker packaging, notification center** —
  still deliberately deferred, per the project's own stated priority
  ("never sacrifice reliability for flashy features"). National-scale OSM
  industrial join, anomaly/baseline detection, audit trail, and model
  versioning metadata — all previously listed here — have since been built
  (see section 17).
- Real satellite imagery (currently: a clearly-labeled "Satellite Evidence
  Preview," never presented as live imagery), Sentinel/higher-resolution
  data, weather/wind data, air-quality data, historical industrial-fire
  records, ground-sensor or drone imagery, active learning.

## 19. National (India-wide) Monitoring

Three geographic levels, per the platform's own staged-architecture
requirement — full AI classification only runs where it's affordable to run:

1. **India** — latest-observations detection layer. State-tagged via a real
   published boundary dataset (GADM-derived, 36 states/UTs, simplified for
   web rendering), 6 map modes (Raw Hotspots, Events, Persistent Sources,
   Industrial Sources, High-Risk, Critical), a Top States by Thermal Activity
   chart, and per-state hotspot/persistent/high-risk counts. No OSM
   industrial join — deliberately, since running that per-hotspot nationally
   on every page load would be prohibitively slow.
2. **State** — filter/zoom into any state from the national view.
3. **Jharkhand–Odisha Belt** — the full detailed pipeline (this README's
   sections 1-18): OSM industrial context, persistence, rule + ML
   classification, risk scoring, alerts, investigation panel.

**A real finding worth knowing:** FIRMS's dedicated `country/csv` endpoint
was found at build time to return `Invalid API call` for every source and
country tried — including NASA's own documented tutorial example curled
directly, independent of anything in this codebase — strongly suggesting the
service is genuinely unavailable server-side right now. The national fetch
falls back to tiling India into ≤8°×8° sub-boxes against the `area/csv`
endpoint (already proven reliable for the regional pipeline), which is why
that's the primary path in practice. See `src/firms/fetch.py`'s
`fetch_country_hotspots()` docstring.

A second real finding from the same testing: a live 2-day fetch for the
primary region legitimately returned zero rows (confirmed via a direct curl,
not a bug) — most likely monsoon-season cloud cover suppressing VIIRS
detections. This is exactly the scenario the dashboard's data-quality note
("absence of a detection does not mean absence of activity") exists for.

**Persistent national history.** Every live national run merges its fresh
~48h pull into a small SQLite store (`data/national_hotspots.db`,
`src/national/store.py`) — never touched in Demo Mode, same isolation
guarantee as the regional store. Persistence is then judged against up to
`NATIONAL_HISTORY_DAYS` (30) of real accumulated history instead of only
ever the latest snapshot, once enough has built up; before that, it falls
back to the single fresh batch. This is detection + persistence only —
the accumulated national history is deliberately **not** run through the
rule engine, ML classifier, or OSM join; that stays reserved for the
Jharkhand–Odisha belt, per the platform's staged-architecture principle
(expensive AI/OSM processing only runs where a user has actually drilled
in). The Data page (India region) shows how many days of history are
currently stored.

To seed a deeper history than incidental app usage would build up on its
own, `scripts/backfill_national_history.py` pulls a full 30-day window
once from a terminal (chunked into ≤5-day requests × ~16 India tiles × 3
VIIRS sources — on the order of a couple hundred requests, several
minutes). Deliberately **not** wired into the live app as a button: that
many sequential HTTP requests is fine to run once ahead of a demo, risky
as an in-app action a judge might click and wait on mid-presentation. Safe
to re-run any time — every row upserts by its natural key.

See `JUDGE_QA.md` for a full Q&A on the platform's design decisions,
including several of the same findings above.

## Scientific Honesty

This platform does not fabricate NASA data, AI accuracy, ground truth,
industrial-fire confirmations, satellite imagery, or government
endorsements. If live data is unavailable, the UI clearly labels the dataset
as demo/cached. Ambiguous classifications are labeled **Requires
Verification** rather than forced into a confident category. Every risk
score and threshold is labeled as a prototype/operational parameter, not an
established standard.
