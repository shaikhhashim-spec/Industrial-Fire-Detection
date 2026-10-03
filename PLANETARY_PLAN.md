# Planetary Thermal Intelligence Work Plan

The public project remains at https://shaikhhashim-spec.github.io/Industrial-Fire-Detection/.
The operational overview is the entry point; the interactive globe lives under `/globe/`.

## Work Distribution

| Owner | Responsibility | Review challenge |
| --- | --- | --- |
| Ingestion agent | Global NASA FIRMS feeds, worldwide reference context, export and scheduled refresh | Prefer bounded global downloads over repeated continent API calls; report incomplete feeds |
| Plume and weather agent | Map hit testing, downwind camera, weather provenance, estimated spread and dossier presentation | Distinguish observed weather from fallback values; do not present a cone as a toxic exposure boundary |
| Interface agent | Region selection, responsive globe layout, filtering, public coverage states | Give the map room while keeping triage controls accessible; preserve India context |
| Main integration agent | Shared event schema, independent feed loading, merge rules, verification and deployment review | Prefer newer observations; preserve richer evidence where dates overlap; check failure states |

## Delivery Sequence

1. Finish plume hover, click, inspection and camera behavior; validate headings and geometry.
2. Add a separate global feed while keeping the India investigation export intact.
3. Filter by region, expose dataset coverage and timestamps, and prioritize the globe in the layout.
4. Add bounded weather enrichment and clearly labeled spread screening for priority events.
5. Run Python, public-page and globe checks; inspect desktop and mobile rendering and interactions.
6. Build with the GitHub Pages project base path and deploy through the existing workflow.

## Scientific Limits

NASA FIRMS reports satellite thermal anomalies. An anomaly alone does not prove a wildfire,
industrial accident or toxic gas release. A nearby power plant is context, not confirmation
of the source. Recent global detections do not carry a 30-day persistence history unless
that history has actually been collected.

The plume is a surface wind direction illustration. Its length is a bounded heuristic,
not a modeled concentration or evacuation radius. The spread score is a screening index,
not the Canadian Fire Weather Index: a true FWI needs fuel moisture state and weather history.
Weather enrichment is capped to keep the public refresh reliable and API usage bounded.

## Follow-On Research

- Accumulate global history before applying persistence claims worldwide.
- Add administrative boundaries for verified country/district attribution; GeoNames city proximity is already available.
- Validate fuel, terrain and moisture inputs before adding fire-front forecasts.
- Replace heuristic cones with a validated dispersion model if concentration estimates are needed.
- Measure larger global feeds before introducing tiled delivery or a streaming service.

## Verified Delivery

On 3 October 2026 the live refresh processed 82,182 recent observations into
39,049 cells, exported 12,000 cells and enriched 30 priority events with weather.
WRI proximity context covers 11,394 thermal facilities, and GeoNames provides
34,107 cities. The India snapshot independently contains 4,478 events.

Desktop (1440 x 900) and mobile (390 x 844) browser checks verified region switching,
investigation selection, plume hover/click, rendered map pixels and motion without
horizontal overflow or runtime errors. The Pages build uses the repository's real
`/Industrial-Fire-Detection/globe/` base path.

## Pure 3D Refactor

- Main integration agent: fixed globe projection, clean model header, left-panel scopes,
  single-instance cinematic camera transitions, preset regression tests and browser QA.
- Navigation agent: remove flat destinations, migrate local saved navigation, and route
  root regional deep links to the globe while retaining Overview for unscoped visits.
- Review decision: geographic presets filter real exports, not synthetic detections.
  Keep export freshness and uncertainty visible outside the model subtitle.
- Added Persian Gulf, national India, North America and Australia camera positions,
  plus South Asia, Jharkhand/Odisha, Permian, Gulf Coast and Pilbara corridor scopes.
- Preserved interactive plume metrics, sixteen-point headings and the 42-degree camera.

## Evidence Arena And Global Redesign

| Owner | Delivery | Independent challenge |
| --- | --- | --- |
| Evidence agent | Shared Sentinel/Skeptic/Arbiter screening, geographic fallback, plume badges and public alert review | No invented glint probabilities, baseline percentiles, cloud state or source confirmation |
| Dashboard agent | Regional branding, search, active plume count, responsive glass surfaces and critical radar state | Global scope must never silently present India-only coverage; reduced motion must work |
| Integration agent | Globe dossier Arena, regional public Alerts, shared module contracts and deployment QA | Both views must use identical evidence arithmetic and preserve plume interactions |

The Arena currently runs deterministic rules, not three independent language models.
Its evidence index is a heuristic, not a calibrated probability, and never changes
the underlying risk score or dispatches an alert. Wind supplies dispersion context,
not proof of industrial origin. Cloud, glint geometry, burn calendars, water masks
and population exposure are unavailable unless collected as explicit evidence.
Actual AI debate requires a protected server-side provider integration, evaluation
against labeled outcomes, and budget/latency controls before operational use.

The user selected rule-based screening for this release. Verification covered
302 Python tests, shared engine and UI tests, regional branding/search, safe
location fallbacks, reduced motion, and desktop/mobile browser interactions.
Plume hover and click remain active. Public assembly excludes tests, Python
cache files and TypeScript declarations from deployed assets.
