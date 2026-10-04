# SIH Demo Runbook

## Before the session

Run from the repository with its virtual environment activated:

```powershell
python scripts/refresh_national_globe.py
python scripts/demo_preflight.py
python start_all.py --no-refresh --no-browser
```

Open http://localhost:8085. Refresh requires working data services; the preflight
reads the existing export without network access. If refresh fails, inspect the
preflight's observation dates before deciding whether the saved run is suitable.
The preflight reports local integrity, not independently verified authenticity.

Keep `output/sih-demo/cache-audit.json`, `sample-incident.html`, and
`sample-incident.txt` available. Build the globe while connected before the
session. `--no-refresh` skips satellite refresh; it does not make map tiles,
weather, imagery, package installation, or external basemaps available offline.
The Events table and incident evidence are the offline presentation path.

## Three-minute presentation

1. **0:00-0:30, Overview:** "We prioritize satellite thermal observations for
   human investigation of industrial fires and persistent heat sources."
   Show source, last observation date, and count. State whether the run is saved.
2. **0:30-1:00, Events:** Search an event ID from the sample incident report.
   Search a location with a category or risk word. Show the matching count and
   export the filtered table.
3. **1:00-1:45, Investigations:** Open that event. Show the satellite detections,
   recurrence, nearby facility, classification evidence, and risk factors.
   Explain that a nearby facility is context rather than confirmation of fire.
4. **1:45-2:15, Globe:** Open the same event on the globe. Explain that both views
   read the same exported observations. If imagery is unavailable, continue with
   the event evidence and coordinates.
5. **2:15-2:45, Report:** Export the incident report. Show observation date,
   classification, evidence, and human-verification requirement.
6. **2:45-3:00, Limits:** Explain missed detections, cloud cover, satellite-pass
   delays, and weak-label evaluation. Finish with the workflow's practical
   benefit: investigators receive a ranked queue with traceable evidence.

## Independent validation

`output/sih-demo/references-pending.json` contains up to 12 real event identities
selected across classification categories. Every label starts unresolved and
uncorroborated. Have a reviewer examine independent imagery, a field report, or
an official incident record; retain its source, date, verifier, and uncertainty.
Do not mark a record verified using this project's rule/model output alone.

Use `src/ml/independent_evaluation.py` to score only corroborated references.
Its input label vocabulary differs from the display categories: prepare explicit
predictions using the documented assessment labels, and retain training
provenance for leakage checks. Report excluded references and sample counts.
Until independent evidence is available, report independent accuracy as pending.

## Questions to rehearse

- **Unavailable FIRMS:** cached real observations with their original dates,
  otherwise a clear error. No synthetic satellite detections.
- **False positives:** examine confidence, recurrence, land-cover and facility
  context; keep uncertain cases unresolved for human review.
- **Resolution and delays:** satellite pixels and overpass intervals constrain
  localization and freshness. Show the acquisition date instead of implying
  a continuously live camera feed.
- **Model accuracy:** rule-label agreement measures reproducibility. Independent
  evidence is required to measure real classification accuracy.
- **Operational use:** the prototype prioritizes review; its risk score is a
  project heuristic and requires field validation before operational adoption.
