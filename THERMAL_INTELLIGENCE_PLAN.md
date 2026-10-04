# Thermal Change And Evidence Review

## Release Scope

Add historical thermal comparison to Investigations and globe dossiers, transparent
review prioritization, evidence-backed assessments, and an independent evaluation
tool. Keep the Arena deterministic. No chatbot, autonomous dispatch, paid hosting,
or automatic training on personal notes is included.

## Agent Assignments

- Data: examine exported observations, implement conservative historical comparison,
  precompute summaries during exports, and test missing/sparse/mixed observations.
- Interface: present change, history coverage, limitations and review priority in
  Investigations and globe details; integrate assessment controls without changing
  the meaning of review status.
- Feedback/evaluation: preserve bounded local/server reviews, record explicit
  assessments and sources separately, and evaluate only independently corroborated
  references. Audit legacy review-to-label overrides.
- Integration/reviewer: challenge assumptions, verify contracts and report exports,
  run tests and browser checks, and document accepted fixes.

## Competing Approaches

Reject per-detection comparisons that confuse additional satellite passes with
heat growth. Reject missing-day zero filling and baselines containing the latest
observation. Prefer comparable observed-day summaries and explicit insufficient
history states. Stable heat is not proof of industrial origin.

Reject review-status-to-ground-truth conversion and accuracy measured against the
same rules that produced training labels. Prefer independently sourced reference
assessments, held-out time/site checks, and explicit insufficient evidence.

## Completion Checks

- Sparse, malformed, duplicate and mixed-sensor observations are handled honestly.
- Priority is an explainable heuristic, not a fire probability.
- Assessment fields survive local import/export and authenticated server review.
- Reports retain provenance, limitations and assessment evidence.
- Existing tests, TypeScript build and desktop/mobile browser checks pass.
- GitHub Pages and the free Render configuration remain supported. Durable training
  history must not depend on temporary Render files.

## Adversarial Decisions

The independent reviewer challenged both exporter/browser parity and evaluation
claims. The accepted design uses matched daily sensor/pass coverage instead of
latest-row statistics. It exposes screening thresholds rather than probabilities.

Resolved findings include preserving sensor metadata, excluding invalid current
observations before display filtering, retaining trusted summaries through feed
merging, safe source/timestamp validation, separating assessment from status, and
including thermal/assessment evidence in CSV, JSON and print reports. Empty
training provenance now cannot validate a holdout, and insufficient class support
prevents an independent-holdout claim. Report labels now say current-day peak,
not latest reading.

Integration additionally found missing-FRP zero coercion upstream and a 24-hour
global feed window. The data work therefore preserves measurement provenance and
accumulates bounded observed history across valid snapshots without promoting
missing days, stale cases, or snapshot omissions into observations.

The final accumulation review also challenged historical same-day substitution
and rows dated after their source event. Imported history must precede the current
acquisition day and stay within the previous event/snapshot date bounds. Current
measurements always come from the current feed. Nullable stored booleans retain
SQL NULL instead of causing migration/import failures or fabricating false values.

## Verification Result

- Full Python suite: 439 passed, one optional PostgreSQL test skipped locally.
- Public frontend: 92 passed with opt-in desktop/mobile browser QA; the optional
  live-backend check was verified separately against a temporary local API.
- Globe: 13 tests passed; TypeScript, lint and production build passed. Six
  existing Fast Refresh lint warnings remain.
- Browser release checks verified real feeds, a controlled heat-change fixture,
  review ranking, local assessment reload, CSV and actual API assessment saves.
- Desktop/mobile globe screenshots and interaction checks passed; sampled canvas
  screenshots contained 2,322 and 1,857 distinct colors respectively.
- Independent final review reported no remaining blockers in the new paths.

Source feed edits present before this task were preserved. This release is local:
no commit/push, GitHub Pages publication, Render deployment, new Docker execution,
or live PostgreSQL check was performed. No new independent reference dataset or
validated production model was invented. Older/sparse feeds retain insufficient
history states until comparable observations exist.
