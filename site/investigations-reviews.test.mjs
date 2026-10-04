import { test } from "node:test";
import assert from "node:assert/strict";
import { assessmentDraft, assessmentTimestamp, safeSource, validateReview, parseReviews, serializeReviews, mergeReviews } from "./investigations-reviews.mjs";

const legacy = { cell: "8512:2012", eventId: "TH-1", status: "reviewed", notes: "", bookmark: false, updatedAt: "2026-10-03T00:00:00Z" };
const assessed = { ...legacy, assessment: "industrial_heat", supportingSources: ["https://example.org/report", "Field report 123"],
  uncertainty: "Exact combustion source uncertain", assessedAt: "2026-10-03T00:00:00.000Z" };

test("Reviewed legacy rows remain compatible and unresolved, never truth", () => {
  assert.deepEqual(validateReview(legacy), legacy);
  assert.equal(assessmentDraft(legacy).assessment, "unresolved");
  assert.equal(assessmentDraft(legacy).assessedAt, null);
  assert.deepEqual(parseReviews(serializeReviews(new Map([[legacy.cell, legacy]]))), [legacy]);
});

test("assessment import/export/merge retains evidence independently of workflow", () => {
  assert.deepEqual(parseReviews(serializeReviews(new Map([[assessed.cell, assessed]]))), [assessed]);
  assert.equal(validateReview({ ...assessed, status: "unreviewed" }).assessment, "industrial_heat");
  const merged = mergeReviews(new Map([[legacy.cell, legacy]]), [{ ...assessed, updatedAt: "2026-10-04T00:00:00Z" }]);
  assert.deepEqual(merged.get(legacy.cell).supportingSources, assessed.supportingSources);
  for (const assessment of ["unresolved", "suspected_fire", "agricultural_burning", "false_positive"]) {
    assert.equal(validateReview({ ...assessed, assessment }).assessment, assessment);
  }
});

test("assessment requires bounded safe evidence, uncertainty and valid time", () => {
  for (const overrides of [ { assessment: "confirmed" }, { assessment: null }, { supportingSources: null },
    { supportingSources: [] }, { uncertainty: " " }, { uncertainty: null }, { uncertainty: "x".repeat(1001) },
    { supportingSources: Array(9).fill("report") }, { supportingSources: ["x".repeat(2049)] },
    { supportingSources: ["javascript:alert(1)"] }, { assessedAt: null }, { assessedAt: "2026-02-30T00:00:00Z" },
    { assessedAt: "2026-10-03T00:00:00" }, { verified: true } ]) assert.throws(() => validateReview({ ...assessed, ...overrides }));
  assert.equal(validateReview({ ...legacy, ...assessmentDraft() }).assessment, "unresolved");
});

test("strict calendar/timezone dates and source controls match backend contract", () => {
  for (const value of ["2024-02-29T12:30:00.123+05:30", "2026-10-03T00:00:00Z"]) assert.ok(assessmentTimestamp(value));
  for (const value of ["2026-02-29T00:00:00Z", "0000-01-01T00:00:00Z", "2026-10-03T24:00:00Z", "2026-10-03T00:00:00+05:99", "2026-10-03T00:00Z"]) assert.equal(assessmentTimestamp(value), false);
  for (const value of ["https://example.org/report", "http://example.org", "Field report <text>", "https://example.org?q=%20"]) assert.ok(safeSource(value));
  for (const value of ["javascript:alert(1)", "data:text/html,x", "//example.org", "https://user:pass@example.org", "https://exam ple.org", "https://example.org:99999", "https://example.org\n", "https:\\example.org", "", "https://%65xample.org", "https:///example.org", "https://@example.org", "report\u0085text", "\u{1f600}".repeat(1025)]) assert.equal(safeSource(value), false);
});
