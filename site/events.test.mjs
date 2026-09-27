import assert from "node:assert/strict";
import { test } from "node:test";
import { COLUMNS, filterEventRows, formatCell, sortRows, toCsv, toRow, toRows } from "./events.mjs";

const event = (over = {}) => ({
  id: "TH-1",
  state: "Gujarat",
  district: "Surat",
  category: "Persistent Industrial Activity",
  riskLevel: "HIGH",
  riskScore: 62,
  frp: 12.34,
  persistenceDays: 6,
  detectionCount: 8,
  corroborated: true,
  latitude: 21.105,
  longitude: 72.646,
  ...over,
});

test("toRow flattens place, facility and reasons the way the dashboard's CSV export does", () => {
  const row = toRow(
    event({
      place: { name: "Surat", distanceKm: 12.4, direction: "NE" },
      facility: { name: "ArcelorMittal", kind: "steel / iron works", distanceKm: 1.1, source: "OpenStreetMap" },
      reasons: ["Peak fire radiative power is 26.5 MW.", "Seen on 17 of the last 30 days."],
    }),
  );
  assert.equal(row.place, "NE 12 km of Surat");
  assert.equal(row.facility, "ArcelorMittal: steel / iron works, 1.1 km (OpenStreetMap)");
  assert.equal(row.reasons, "Peak fire radiative power is 26.5 MW. Seen on 17 of the last 30 days.");
  assert.equal(row.corroborated, "Yes");
});

test("a place under 1 km, or missing, reads as the place name or blank, not a distance", () => {
  assert.equal(toRow(event({ place: { name: "Surat", distanceKm: 0.4, direction: "NE" } })).place, "Surat");
  assert.equal(toRow(event({ place: null })).place, "");
  assert.equal(toRow(event({ facility: null })).facility, "");
  assert.equal(toRow(event({ reasons: undefined })).reasons, "");
});

test("corroborated is only No when the event says so explicitly", () => {
  assert.equal(toRow(event({ corroborated: false })).corroborated, "No");
  assert.equal(toRow(event({ corroborated: undefined })).corroborated, "Yes");
});

test("toRows maps every event, and every column has a row key", () => {
  const rows = toRows([event({ id: "A" }), event({ id: "B" })]);
  assert.deepEqual(rows.map((r) => r.id), ["A", "B"]);
  for (const col of COLUMNS) assert.ok(col.key in rows[0], col.key);
});

test("filterEventRows matches id, place and category, all rows for an empty query", () => {
  const rows = toRows([event({ id: "A", state: "Gujarat" }), event({ id: "B", state: "Kerala" })]);
  assert.deepEqual(filterEventRows(rows, "kerala").map((r) => r.id), ["B"]);
  assert.deepEqual(filterEventRows(rows, "  ").map((r) => r.id), ["A", "B"]);
  assert.deepEqual(filterEventRows(rows, ""), rows);
});

test("sortRows sorts numeric columns numerically and text columns as text", () => {
  const rows = toRows([event({ id: "A", riskScore: 40 }), event({ id: "B", riskScore: 90 }), event({ id: "C", riskScore: 10 })]);
  assert.deepEqual(sortRows(rows, "riskScore", "desc").map((r) => r.id), ["B", "A", "C"]);
  assert.deepEqual(sortRows(rows, "riskScore", "asc").map((r) => r.id), ["C", "A", "B"]);
  assert.deepEqual(sortRows(rows, "id", "asc").map((r) => r.id), ["A", "B", "C"]);
});

test("sortRows does not mutate its input", () => {
  const rows = toRows([event({ id: "A", riskScore: 1 }), event({ id: "B", riskScore: 2 })]);
  sortRows(rows, "riskScore", "desc");
  assert.deepEqual(rows.map((r) => r.id), ["A", "B"]);
});

test("formatCell rounds risk score, keeps one decimal on FRP, and four on coordinates", () => {
  const col = (key) => COLUMNS.find((c) => c.key === key);
  assert.equal(formatCell(col("riskScore"), 61.7), "62");
  assert.equal(formatCell(col("frp"), 12.34), "12.3");
  assert.equal(formatCell(col("latitude"), 21.10456), "21.1046");
  assert.equal(formatCell(col("state"), "Gujarat"), "Gujarat");
  assert.equal(formatCell(col("district"), null), "");
});

test("toCsv quotes values that contain a comma and matches the column labels", () => {
  const rows = toRows([event({ reasons: ["Contains, a comma"] })]);
  const csv = toCsv(rows);
  assert.ok(csv.startsWith("Event,State,District,Nearest place"));
  assert.ok(csv.includes('"Contains, a comma"'));
});
