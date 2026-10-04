import test from "node:test";
import assert from "node:assert/strict";
import { analyzeThermalChange } from "./thermal-change.mjs";
import { investigationPriority, normalizeEvent, queryCases, globeLink, cellKey, mergeFeeds } from "./investigations-data.mjs";
import { reportSnapshot, reportCsv } from "./investigations-reports.mjs";

const event = (over = {}) => ({ id: "A", latitude: 20, longitude: 85, acqDate: "2026-10-04",
  category: "Persistent Industrial Activity", riskScore: 90, riskLevel: "HIGH", persistenceDays: 4,
  satellite: "VIIRS S-NPP", daynight: "N", history: [5, 5, 5, 40].map((frp, i) => ({
    date: `2026-10-0${i + 1}`, frp, satellite: "VIIRS S-NPP", instrument: "VIIRS", daynight: "N", confidence: 80,
  })), ...over });

test("normalization retains sensor/pass coverage and exclusions for shared thermal analysis", () => {
  const raw = event(), clean = normalizeEvent(raw);
  assert.deepEqual(analyzeThermalChange(clean), analyzeThermalChange(raw));
  assert.equal(investigationPriority(clean).thermal.status, "elevated");
  raw.history.at(-1).synthetic = true;
  assert.deepEqual(analyzeThermalChange(normalizeEvent(raw)), analyzeThermalChange(raw));
  assert.equal(investigationPriority(normalizeEvent(raw)).thermal.status, "insufficient_history");
  assert.equal(normalizeEvent(event({ historyTruncated: true })).historyTruncated, true);
});

test("priority explains anomalies, unexplained labels and disagreement without model probability", () => {
  const result = investigationPriority(event({ category: "Requires Verification",
    model: { agrees: false, label: "Persistent Industrial Activity", confidence: .99 } }));
  assert.equal(result.points, result.thermal.priorityPoints + 25 + 20);
  assert.deepEqual(result.contributions.map((c) => c.label), ["Thermal anomaly", "Unexplained label", "Conflicting labels"]);
  assert.match(result.caveat, /not fire probability/);
  for (const model of [{ agrees: false, label: "Persistent Industrial Activity", confidence: .9 },
    { agrees: false, label: "Likely Wildfire", confidence: 90 },
    { agrees: true, label: "Likely Wildfire", confidence: .9 }]) {
    assert.equal(investigationPriority(event({ history: [], model })).points, 0);
  }
  assert.equal(investigationPriority(event({ history: [] })).thermal.status, "insufficient_history");
});

test("normalization computes summary from original coverage and ignores forged summaries through merge", () => {
  const raw = event({ thermalChange: { status: "elevated", priorityPoints: 10000 } });
  raw.history.push({ date: "2026-10-04", frp: null, satellite: "VIIRS S-NPP", daynight: "N" });
  const clean = normalizeEvent(raw), expected = analyzeThermalChange(raw);
  assert.deepEqual(clean.thermalChange, expected);
  assert.deepEqual(investigationPriority(clean).thermal, expected);
  const merged = mergeFeeds([{ name: "national", events: [clean], meta: { source: "firms_live" } }])[0];
  assert.deepEqual(merged.thermalChange, expected);
  assert.deepEqual(investigationPriority(merged).thermal, expected);
  assert.equal(investigationPriority(merged).points, 0);
  assert.equal(expected.status, "insufficient_history");
});

test("multiple current sensor groups require comparable historical coverage", () => {
  const raw = event();
  raw.history.push({ date: "2026-10-04", frp: 50, satellite: "VIIRS NOAA-20", daynight: "N" });
  const result = investigationPriority(normalizeEvent(raw));
  assert.equal(result.thermal.status, "insufficient_history");
  assert.equal(result.thermal.baselineFrp, null);
  assert.equal(result.thermal.priorityPoints, 0);
  assert.equal(result.thermal.observationDays, 0);
});

test("normalized thermal summary reaches JSON and CSV with independent analyst fields", () => {
  const clean = normalizeEvent(event());
  const reviews = new Map([[cellKey(clean), { status: "reviewed", assessment: "suspected_fire",
    supportingSources: ["Field observation"], uncertainty: "Cause is unverified", assessedAt: "2026-10-04T08:00:00Z" }]]);
  const snapshot = reportSnapshot([clean], reviews, "india"), csv = reportCsv(snapshot);
  assert.deepEqual(snapshot.cases[0].event.thermalChange, analyzeThermalChange(event()));
  for (const text of ["Elevated thermal output", '"5"', '"40"', '"700"', "suspected_fire", "Field observation", "Cause is unverified", "2026-10-04T08:00:00Z"])
    assert.ok(csv.includes(text), text);
  assert.equal(snapshot.cases[0].event.category, "Persistent Industrial Activity");
  assert.equal(snapshot.cases[0].review.status, "reviewed");
});

test("priority ordering preserves explicit sorts, combined filters, bookmarks and links", () => {
  const stable = event({ id: "stable", longitude: 85.1, history: [], riskScore: 99 });
  const anomaly = event({ id: "anomaly", longitude: 85.2, riskScore: 10 });
  const unexplained = event({ id: "unexplained", longitude: 85.3, history: [], riskScore: 5, category: "Requires Verification" });
  const rows = [stable, anomaly, unexplained], original = [...rows];
  assert.deepEqual(queryCases(rows).map((e) => e.id), ["unexplained", "anomaly", "stable"]);
  assert.deepEqual(queryCases(rows, { sort: "priority", direction: "asc" }).map((e) => e.id), ["stable", "anomaly", "unexplained"]);
  assert.deepEqual(queryCases(rows, { sort: "risk" }).map((e) => e.id), ["stable", "anomaly", "unexplained"]);
  const reviews = new Map([[cellKey(anomaly), { bookmark: true, status: "in-review" }]]);
  assert.deepEqual(queryCases(rows, { bookmarks: true, status: "in-review", severity: "HIGH", persistence: "4", search: "anomaly" }, reviews), [anomaly]);
  assert.deepEqual(rows, original);
  assert.equal(new URL(globeLink(anomaly, "india"), "https://example.org/").searchParams.get("event"), "anomaly");
  assert.deepEqual(queryCases([event({ id: "B", history: [], riskScore: null }), event({ id: "A", history: [], riskScore: null })]).map((e) => e.id), ["A", "B"]);
});
