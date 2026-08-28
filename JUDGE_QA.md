# Judge Q&A — SIH26162 Thermal Intelligence Platform

Honest, technically accurate answers, written to be easy for the team to explain live.

**1. Why NASA FIRMS?**
It's free, global, updated multiple times daily, and provides exactly the fields a
detection pipeline needs (lat/lon, brightness, FRP, confidence, acquisition
time, satellite/instrument) with no licensing cost — the only realistic choice
for a free-data-only prototype at this scale.

**2. Why persistence detection?**
A single hotspot tells you almost nothing — it could be a flare, sun glint, or a
one-off wildfire. A location that keeps recurring over days is a fundamentally
different, more actionable signal. This is also the platform's own headline
story: Jharia's coal-seam fires have burned for decades — exactly the
"persistent thermal source" pattern the platform is built to surface.

**3. Why a 1km grid?**
It's a pragmatic match to VIIRS's ~375m pixel footprint (roughly 1km when you
account for detection jitter) — fine enough to separate distinct industrial
sites, coarse enough that the same real-world source doesn't get split across
many grid cells from small coordinate noise between passes.

**4. Why VIIRS/MODIS?**
Both are free, NASA-operated, and complementary: VIIRS (SNPP, NOAA-20, NOAA-21)
gives finer spatial resolution and more frequent revisits; MODIS gives a longer
historical record. Combining sources gives denser coverage than any single
sensor.

**5. How does the AI classify a hotspot?**
Two layers. First, an explainable rule engine combines confidence, FRP,
persistence, and industrial-zone proximity into one of 8 categories, each with
a plain-language reason and an evidence list — this is the platform's primary,
trustworthy signal. Second, a Random Forest is trained on the rule engine's own
output as a validation/feature-importance layer, not a replacement.

**6. Where did training labels come from?**
The rule engine's own output — "weak labels," explicitly not human-verified
ground truth. This is disclosed everywhere the ML metrics are shown, not just
here.

**7. How do you validate the model?**
On a held-out split of the rule-labeled data (accuracy/precision/recall/F1/
confusion matrix, all genuinely computed, never fabricated) — but that measures
agreement with the rule engine, not confirmed real-world accuracy. Real
validation would need a manually verified ground-truth dataset, which is listed
as a limitation, not glossed over.

**8. What happens when FIRMS is unavailable?**
A fallback hierarchy: **live API → local cache → demo dataset.** This isn't
theoretical — during development, the public Overpass (OSM) endpoint returned a
504 mid-session and the app fell back to its cache automatically with no code
change needed. Separately, a live 2-day FIRMS pull legitimately returned zero
rows for the primary region (most likely monsoon cloud cover) — the pipeline
correctly fell through to demo data rather than showing a broken page.

**9. Can the system detect every fire?**
No, and it doesn't claim to. Small fires, fires under cloud cover or smoke, and
fires between satellite passes can be missed entirely. This is stated directly
in the dashboard's Methodology & Limitations section.

**10. How do you handle false positives?**
The rule engine has an explicit `Sun Glint / False Positive` category (low
confidence, single-day, non-industrial, outside burn season) and a
`Requires Verification` category for anything that doesn't cleanly match a
rule — ambiguous cases are labeled as ambiguous rather than forced into a
confident-sounding bucket.

**11. How do you distinguish normal industrial activity from abnormal activity?**
`Persistent Industrial Activity` (recurring, below the fire-intensity bar) is
treated as a separate, lower-urgency category from `Likely Industrial Fire`
(recurring AND high FRP/confidence). This distinction came directly from a real
calibration finding: an FRP threshold set from plausible-sounding textbook
numbers turned out to be above the 99th percentile of real observed data,
leaving 81% of real detections unclassified until it was recalibrated and this
category was added.

**12. How does the risk score work?**
A weighted 0–100 blend of persistence (30%), FRP (25%), satellite confidence
(20%), industrial proximity (15%), and recent recurrence (10%) — each
component independently normalized before weighting, all configurable. It's
labeled a "Prototype Operational Risk Score," explicitly not an official
government standard.

**13. Why use OpenStreetMap?**
Free, no API key, and has real tagged industrial/mining/power-plant data for
this region — over 2,000 zones were pulled live for the Jharkhand–Odisha belt
during testing.

**14. How does the system scale?**
Region-independent by design: `config.REGIONS` holds region definitions rather
than hard-coding bounding boxes throughout the code. The national (India-wide)
layer already demonstrates this — it runs the same fetch/clean/grid pipeline
country-wide, deliberately staged to skip the expensive per-hotspot OSM join
(which only makes sense once a user drills into a specific industrial belt).

**15. What happens if OSM data is incomplete?**
Classification continues using the features that are available — the pipeline
degrades gracefully rather than failing outright, and a hotspot outside any
mapped zone just gets `zone_type="other"`, which the rule engine already
accounts for.

**16. How do analysts verify an alert?**
The investigation panel shows the full evidence trail behind a classification
(which specific conditions fired), historical FRP activity for that location,
and a downloadable incident report — everything needed to sanity-check the
system's reasoning before acting on it.

**17. What is the difference between observation and event?**
An **observation** is one satellite detection. An **event/source** is a
spatial-temporal grouping of observations at the same ~1km cell. The dashboard
shows both counts explicitly (e.g. national mode: "Satellite Hotspots" vs.
"Detected Events") specifically so raw detection counts are never confused
with distinct real-world sources.

**18. How could this be deployed nationally?**
The national layer already exists as a working (not hypothetical) staged
architecture: India-wide detection with state tagging via real published
boundary data, drilling down into any region for full geospatial + AI
analysis — the same pattern used for Jharkhand–Odisha could be replicated for
any other industrial belt by adding an entry to the region registry.

**19. What are the current limitations?**
No forest/water/agricultural-zone OSM layers (deliberately skipped for
reliability — see README), no persistent alert-history/dismiss-state store, no
SHAP explanations, plain-text (not PDF) incident reports, no real satellite
imagery (a clearly labeled preview only), and model evaluation is against weak
labels, not verified ground truth.

**20. What would you add with more time?**
A manually validated ground-truth dataset for real accuracy measurement,
persistent audit-trail/model-versioning records for reproducibility, a
human-in-the-loop review queue that feeds back into training, and forest/
water/agricultural OSM layers once a more reliable Overpass mirror or cached
extract is available.
