# Offline independent evaluation

Run from the repository root:

```powershell
python -m src.ml.independent_evaluation evaluation-input.json --minimum-labels 10
```

This scores supplied predictions; it trains no model and does not fetch sources.
It reports per-category precision, recall, confusion counts, individual errors,
excluded references, unscored predictions and insufficient reference counts.
It does not report rule agreement as real-world accuracy. Undefined precision or
recall is JSON `null`, not an invented zero. Missing predictions and unresolved
predictions count as misses for reference recall.

Input example (illustrative records, not real evidence):

```json
{
  "predictions": [
    {
      "eventId": "case-1",
      "siteId": "facility-17",
      "observedAt": "2026-10-03T00:00:00Z",
      "label": "industrial_heat"
    }
  ],
  "references": [
    {
      "eventId": "case-1",
      "siteId": "facility-17",
      "observedAt": "2026-10-03T00:00:00Z",
      "label": "industrial_heat",
      "independentlyCorroborated": true,
      "referenceType": "field_report",
      "supportingSources": ["Independent field visit record 123"],
      "verifiedBy": "independent-inspector",
      "verifiedAt": "2026-10-04T00:00:00Z"
    }
  ],
  "trainingRecords": [
    {
      "eventId": "earlier-case",
      "siteId": "different-facility",
      "observedAt": "2026-09-01T00:00:00Z"
    }
  ]
}
```

Prediction labels are `unresolved`, `industrial_heat`, `suspected_fire`,
`agricultural_burning`, or `false_positive`. References must have one of the four
non-unresolved labels. Each record requires an event ID, a stable physical-site ID
and an observation timestamp. Timestamps require calendar-valid dates, seconds,
an explicit timezone, and optionally 1-3 fractional-second digits.

Only literal `independentlyCorroborated: true`, a reference type of `field_report`,
`independent_imagery`, or `official_incident_record`, a named verifier, verification
timestamp and 1-8 bounded safe source strings qualify a reference. Unverified,
rule-derived or analyst-only references are excluded with reasons. The curator
must establish that the underlying evidence is independent of the supplied
predictions and actually supports the category. This utility validates that
assertion's structure; it cannot authenticate the evidence or establish source
independence from links alone. Workflow Reviewed/Rejected and ordinary analyst
assessments do not supply this assertion and never become training truth.

`trainingRecords` is optional provenance for the predictor, not training input.
When supplied, the report detects shared event IDs, shared sites, and reference
observations at or before the latest training observation. Use a consistent
physical-site identity across nearby cells; cell IDs alone can hide site leakage.
Invalid training provenance is reported and prevents a valid holdout assertion.
When omitted or empty, ML separation is explicitly unknown and is never validated.
For an untrained heuristic, training holdout validation is not applicable. Leakage
counts remain visible alongside descriptive metrics. `separationValidated` requires
nonempty valid provenance without leakage; `coverageSufficient` requires every
category to meet the requested minimum support. `validIndependentHoldout` requires
both. These structural checks do not establish evidence quality or scientific
sufficiency, and produce no confidence estimates.

Use `--minimum-labels` to set the desired minimum support per category. The
default of one detects absent classes and is not a scientific sufficiency claim.
Precision uses only predictions paired with accepted references; unmatched
predictions are reported as unscored, never assumed to be false positives.
Matching event IDs with different sites or observation times are errors.
Duplicate event IDs and invalid prediction records reject the input.
