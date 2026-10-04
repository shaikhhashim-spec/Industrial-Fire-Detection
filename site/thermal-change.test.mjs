import test from "node:test";
import assert from "node:assert/strict";
import { analyzeThermalChange } from "./thermal-change.mjs";

const row = (date, frp, extra = {}) => ({ date, frp, satellite: "N20", instrument: "VIIRS", daynight: "N", ...extra });
const event = (current = 30) => ({ acqDate: "2026-10-04", frp: 999,
  history: [row("2026-10-01", 10), row("2026-10-02", 12), row("2026-10-03", 8), row("2026-10-04", current)] });

test("daily baseline excludes all current readings and ignores the window peak", () => {
  const e = event();
  e.history.push(row("2026-10-04", 20));
  const result = analyzeThermalChange(e);
  assert.equal(result.baselineFrp, 10);
  assert.equal(result.currentFrp, 30);
  assert.equal(result.changePercent, 200);
  assert.equal(result.observationDays, 3);
  assert.equal(result.status, "elevated");
  assert.equal(result.priorityPoints, 10);
  assert.match(result.limitations.join(" "), /not confirmation of fire/);
});

test("duplicate rows and input ordering do not overweight a day", () => {
  const e = event();
  e.history.push(...Array.from({ length: 100 }, () => row("2026-10-01", 1)));
  assert.deepEqual(analyzeThermalChange(e), analyzeThermalChange(event()));
  e.history.reverse();
  assert.deepEqual(analyzeThermalChange(e), analyzeThermalChange(event()));
});

test("one busy prior day is insufficient even with many detections", () => {
  const e = event();
  e.history = [...Array.from({ length: 100 }, () => row("2026-10-03", 10)), row("2026-10-04", 30)];
  const result = analyzeThermalChange(e);
  assert.equal(result.status, "insufficient_history");
  assert.equal(result.observationDays, 1);
  assert.equal(result.changePercent, null);
  assert.equal(result.priorityPoints, 0);
});

test("missing calendar dates never enter the baseline as zero", () => {
  const e = event(10);
  e.history[0].date = "2026-09-20";
  const result = analyzeThermalChange(e);
  assert.equal(result.baselineFrp, 10);
  assert.equal(result.gaps, 11);
  assert.equal(result.status, "stable");
  assert.match(result.label, /Recurring thermal activity/);
  assert.doesNotMatch(result.label, /industrial/i);
});

test("every current satellite and pass group needs prior coverage", () => {
  for (const extra of [{ satellite: "N21" }, { daynight: "D" }, { satellite: "Aqua", instrument: "MODIS" }]) {
    const e = event();
    e.history.push(row("2026-10-04", 50, extra));
    assert.equal(analyzeThermalChange(e).status, "insufficient_history");
    for (const date of ["2026-10-01", "2026-10-02", "2026-10-03"]) e.history.push(row(date, 10, extra));
    assert.equal(analyzeThermalChange(e).status, "elevated");
  }
});

test("old feeds cannot borrow event-level sensor metadata", () => {
  const e = event();
  e.satellite = "VIIRS NOAA-20";
  e.history = e.history.map(({ date, frp }) => ({ date, frp }));
  assert.equal(analyzeThermalChange(e).status, "insufficient_history");
  assert.equal(analyzeThermalChange(e).currentFrp, null);
});

test("malformed or incomplete current observations prevent a verdict", () => {
  for (const extra of [{ frp: null }, { frp: -1 }, { frp: "30" }, { frp: NaN }, { frp: Infinity },
    { synthetic: true }, { satellite: "MODIS_NRT" }, { instrument: "MODIS" }, { daynight: null }]) {
    const e = event();
    e.history.push(row("2026-10-04", 30, extra));
    assert.equal(analyzeThermalChange(e).status, "insufficient_history");
  }
  assert.equal(analyzeThermalChange({ ...event(), acqDate: "2026-02-30" }).status, "insufficient_history");
  assert.equal(analyzeThermalChange({ ...event(), historyTruncated: true }).status, "insufficient_history");
  assert.equal(analyzeThermalChange(null).status, "insufficient_history");
});

test("invalid prior measurements invalidate that day, not a zero baseline", () => {
  const e = event();
  e.history.push(row("2026-10-03", null));
  const result = analyzeThermalChange(e);
  assert.equal(result.status, "insufficient_history");
  assert.equal(result.observationDays, 2);
  assert.equal(result.gaps, 1);
});

test("future, out-of-window and zero-only baselines do not create an alarm", () => {
  const e = event();
  e.history.push(row("2026-10-05", 9999), row("2026-09-03", 9999));
  assert.deepEqual(analyzeThermalChange(e), analyzeThermalChange(event()));
  e.history = e.history.slice(0, 4).map(r => r.date === e.acqDate ? r : { ...r, frp: 0, frpObserved: true });
  const result = analyzeThermalChange(e);
  assert.equal(result.baselineFrp, 0);
  assert.equal(result.changePercent, null);
  assert.equal(result.status, "insufficient_history");
});

test("unmarked zeros and explicit unobserved values cannot depress the baseline", () => {
  for (const extra of [{ frp: 0 }, { frp: 0, frpObserved: false }, { frp: 1, frpObserved: false }]) {
    const e = event(15);
    Object.assign(e.history[0], extra);
    const result = analyzeThermalChange(e);
    assert.equal(result.status, "insufficient_history");
    assert.equal(result.observationDays, 2);
    assert.match(result.limitations.join(" "), /measurement provenance/);
  }
  const e = event(15);
  Object.assign(e.history[0], { frp: 0, frpObserved: true });
  assert.equal(analyzeThermalChange(e).observationDays, 3);
  assert.equal(analyzeThermalChange(e).baselineFrp, 8);
});

test("relative and absolute thresholds are both necessary", () => {
  assert.equal(analyzeThermalChange(event(15)).status, "elevated");
  assert.equal(analyzeThermalChange(event(14.9)).status, "stable");
  assert.equal(analyzeThermalChange(event(5)).status, "reduced");
  const e = event(3);
  e.history = e.history.map(r => r.date === e.acqDate ? r : { ...r, frp: 1 });
  assert.equal(analyzeThermalChange(e).status, "stable");
});

test("known aliases and inferred instrument match without mutating input", () => {
  const e = event();
  e.history[3].satellite = "VIIRS NOAA-20";
  delete e.history[3].instrument;
  const before = structuredClone(e);
  assert.deepEqual(analyzeThermalChange(e), analyzeThermalChange(event()));
  assert.deepEqual(e, before);
});
