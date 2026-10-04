# Thermal Change And Evidence Review

## Historical Comparison

Investigations and globe dossiers use the same screening contract. The current
acquisition day's peak FRP is compared with the median of prior daily peaks in
the preceding 30 days. At least three prior days must cover every current
satellite/instrument/day-night group. Current-day samples never enter the baseline.
More detections on one day do not add baseline days.

Elevated output requires both a 50% increase and a 5 MW increase. Reduced output
requires both a one-third decrease and a 5 MW decrease. These are provisional
screening thresholds, not calibrated probabilities. Stable output means recurring
thermal activity, not proof of industrial origin or safety. Cloud/overpass/pixel
coverage remains an uncertainty even with matching sensor groups.

Missing, synthetic, incomplete or incompatible observations cannot be zero-filled.
Older snapshots without pass metadata show insufficient history. The baseline is
limited to observations actually exported, not a claim of continuous monitoring.
Measurement provenance distinguishes valid readings from cleaner placeholders;
legacy zeros without that provenance are conservatively excluded. Global history
accumulation depends on previous snapshots being retained, which the Pages cache
supports but does not guarantee. Cache loss means less history, never zero heat.

## Review Ordering

The default investigation queue sorts by explainable review-priority points:

- Elevated thermal output: 10.
- Requires Verification rule label: 25.
- Persistent non-industrial thermal source rule label: 15.
- Valid rule/model label disagreement: 20.

Unexplained labels deliberately outweigh change alone. Ties use risk score and
event ID. Existing risk, time, persistence and FRP sorts remain available. Priority
does not change operational severity, establish cause or trigger dispatch.

## Analyst Assessments

Workflow status, notes and bookmarks remain separate from assessment. Assessment
categories are unresolved, industrial heat, suspected fire, agricultural burning,
and false positive. Non-unresolved assessments require supporting sources,
uncertainty and an assessment timestamp. Sources are bounded plain text or safe
HTTP(S) URLs. Neither a link nor a reviewed status proves independent verification.

Local review import/export remains backward compatible. Authenticated server
reviews retain these fields and audit/version checks. Free Render server state is
temporary; back up annotations and keep independently curated references outside
temporary server files. No automatic training occurs.

## Independent Evaluation

Run the evaluator on a separately curated JSON file:

```powershell
python -m src.ml.independent_evaluation path/to/reference-evaluation.json --minimum-labels 10
```

The input has `predictions`, `references`, and optional `trainingRecords` arrays.
Each prediction contains `eventId`, `siteId`, timezone-qualified `observedAt`, and
`label` using an assessment category. Each reference additionally requires
`independentlyCorroborated: true`, `referenceType` (field_report,
independent_imagery, or official_incident_record), `supportingSources`, `verifiedBy`,
and timezone-qualified `verifiedAt`. Training records need event/site/time identity.

The utility reports per-class precision/recall, confusion, errors, excluded
references, insufficient labels and supplied time/site/event overlap. Missing or
empty training provenance cannot validate an ML holdout. The utility cannot
authenticate a curator's evidence assertion. It trains no model, supplies no new
probabilities, and does not establish operational accuracy from a small sample.

## Static Build

Pipeline exports precompute `thermalChange`. Older snapshots can be enriched on
separate assembled copies without ingestion:

```powershell
python scripts/assemble_pages_site.py --out _site
python scripts/precompute_thermal_site.py --site _site
```

Pages and Docker run this during build, not server startup. Source feeds are not
overwritten. The browser independently computes the same contract, which also
keeps older snapshots usable without trusting arbitrary precomputed feed fields.
This release does not provision durable cloud history, paid resources, a chatbot,
or a newly trained/validated classifier.
