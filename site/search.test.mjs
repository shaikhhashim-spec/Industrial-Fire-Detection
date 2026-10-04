import assert from "node:assert/strict";
import { test } from "node:test";
import { matchesSearch } from "./search.mjs";
import { filterEventRows, toRows } from "./events.mjs";
import { matchAlerts } from "./overview.mjs";
import { queryCases } from "./investigations-data.mjs";

test("words match across fields, case, accents and repeated spaces; regex is literal", () => {
  assert.equal(matchesSearch(["Cafe\u0301", "HIGH", "TH-[1]"], "  CAFE   high [1] "), true);
  assert.equal(matchesSearch(["Odisha", "Industrial"], "Odisha wildfire"), false);
  assert.equal(matchesSearch(["Odisha"], ".*"), false);
  assert.equal(matchesSearch([null], " "), true);
});

test("global Events search includes country, region and risk", () => {
  const rows = toRows([{ id: "A", country: "Brazil", region: "Para", riskLevel: "HIGH" }]);
  assert.equal(filterEventRows(rows, "brazil high").length, 1);
  assert.equal(filterEventRows(rows, "para brazil").length, 1);
});

test("alerts and investigations accept location plus classification words", () => {
  assert.equal(matchAlerts([{ id: "A", state: "Odisha", classification: "Industrial", severity: "HIGH" }], "Odisha industrial high").length, 1);
  const events = [{ id: "A", latitude: 22, longitude: 85, state: "Odisha", category: "Industrial", riskLevel: "HIGH" }];
  assert.equal(queryCases(events, { region: "global", search: "odisha high industrial" }).length, 1);
});
