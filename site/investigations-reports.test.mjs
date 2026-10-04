import { test } from "node:test";
import assert from "node:assert/strict";
import { reportCsv, reportSnapshot } from "./investigations-reports.mjs";

test("reports retain thermal limitations and separate assessment from workflow status", () => {
  const event = { id: "case-1", longitude: 85, latitude: 22, thermalChange: {
    label: "Rising activity", baselineFrp: 10, currentFrp: 25, changePercent: 150,
    observationDays: 4, gaps: 2, limitations: ["Cloud context unavailable"],
  } };
  const review = { status: "reviewed", assessment: "suspected_fire",
    supportingSources: ["https://example.org/independent-observation"], uncertainty: "Cause unresolved", assessedAt: "2026-10-04T00:00:00Z" };
  const report = reportSnapshot([event], new Map([["8500:2200", review]]), "india");
  const csv = reportCsv(report);
  assert.match(csv, /Analyst assessment \(not verified truth\)/);
  assert.match(csv, /"reviewed"/);
  assert.match(csv, /"suspected_fire"/);
  assert.match(csv, /Cloud context unavailable/);
  assert.match(csv, /independent-observation/);
  assert.equal(report.cases[0].review.assessment, "suspected_fire");
  assert.equal(report.cases[0].event.thermalChange.changePercent, 150);
});
