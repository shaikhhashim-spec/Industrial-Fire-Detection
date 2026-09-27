import assert from "node:assert/strict";
import { test } from "node:test";
import {
  categoryCounts,
  frpHistogram,
  persistenceCounts,
  riskCounts,
  satelliteCounts,
  topStates,
} from "./analytics.mjs";

const event = (over = {}) => ({
  category: "Persistent Industrial Activity",
  riskLevel: "MODERATE",
  state: "Gujarat",
  satellite: "VIIRS NOAA-20",
  frp: 5,
  persistenceDays: 1,
  ...over,
});

test("categoryCounts ranks by count, most active first, and colors by the fixed category map", () => {
  const events = [
    event({ category: "Likely Wildfire" }),
    event({ category: "Likely Wildfire" }),
    event({ category: "Requires Verification" }),
  ];
  const counts = categoryCounts(events);
  assert.deepEqual(
    counts.map((c) => [c.label, c.count]),
    [
      ["Likely Wildfire", 2],
      ["Requires Verification", 1],
    ],
  );
  assert.equal(counts[0].color, "#008300");
});

test("riskCounts is always low-to-critical, even with zero counts, and never sorted by count", () => {
  const counts = riskCounts([event({ riskLevel: "CRITICAL" }), event({ riskLevel: "CRITICAL" })]);
  assert.deepEqual(
    counts.map((c) => [c.label, c.count]),
    [
      ["Low", 0],
      ["Moderate", 0],
      ["High", 0],
      ["Critical", 2],
    ],
  );
  assert.equal(counts[3].color, "#d03b3b");
});

test("topStates ranks states by hotspot count and caps at n, using the single series colour", () => {
  const events = [
    ...Array(3).fill(event({ state: "Gujarat" })),
    ...Array(5).fill(event({ state: "Karnataka" })),
    event({ state: "Kerala" }),
  ];
  const top = topStates(events, 2);
  assert.deepEqual(top.map((s) => [s.label, s.count]), [
    ["Karnataka", 5],
    ["Gujarat", 3],
  ]);
  assert.equal(top[0].color, "#3987e5");
});

test("satelliteCounts uses the full sensor name and ranks by count", () => {
  const events = [event({ satellite: "MODIS Aqua" }), event({ satellite: "VIIRS S-NPP" }), event({ satellite: "VIIRS S-NPP" })];
  assert.deepEqual(
    satelliteCounts(events).map((s) => s.label),
    ["Suomi NPP VIIRS", "Aqua MODIS"],
  );
});

test("frpHistogram bins into clean widths, most intense bin last, and is empty with no data", () => {
  const events = [event({ frp: 1 }), event({ frp: 4 }), event({ frp: 19 })];
  const bins = frpHistogram(events, 4);
  assert.equal(bins.reduce((s, b) => s + b.count, 0), 3);
  assert.ok(bins[bins.length - 1].label.endsWith("+ MW"));
  assert.deepEqual(frpHistogram([]), []);
});

test("persistenceCounts buckets days active into the product's usual bands", () => {
  const events = [
    event({ persistenceDays: 0 }),
    event({ persistenceDays: 5 }),
    event({ persistenceDays: 5 }),
    event({ persistenceDays: 30 }),
    event({ persistenceDays: 90 }),
  ];
  const counts = persistenceCounts(events);
  assert.deepEqual(
    Object.fromEntries(counts.map((c) => [c.key, c.count])),
    { "0": 1, "1": 0, "2–3": 0, "4–6": 2, "7–13": 0, "14–29": 0, "30+": 2 },
  );
});
