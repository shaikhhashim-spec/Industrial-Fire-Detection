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
