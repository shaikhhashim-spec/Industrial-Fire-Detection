import assert from "node:assert/strict";
import { test } from "node:test";
import { alertsFrom, fmtAge, fmtUpdated, matchAlerts, satelliteLabel, summarize, urgencyColor } from "./overview.mjs";

const event = (over = {}) => ({
  id: "TH-1",
  riskLevel: "MODERATE",
  riskScore: 40,
  state: "Gujarat",
  region: "Hajira INA, Gujarat",
  district: "Surat",
  category: "Persistent Industrial Activity",
  satellite: "VIIRS NOAA-20",
  persistenceDays: 1,
  latitude: 21.1,
  longitude: 72.6,
  frp: 5,
  ...over,
});

const sample = () => ({
  meta: { generatedAt: "2026-09-25T17:55:30Z" },
  events: [
    event({ id: "A", riskLevel: "CRITICAL", riskScore: 80, priority: 1, persistenceDays: 17, facility: { name: "Steel" } }),
    event({ id: "B", riskLevel: "CRITICAL", riskScore: 80, priority: 2, persistenceDays: 17 }),
    event({ id: "C", riskLevel: "HIGH", riskScore: 70, state: "Karnataka", satellite: "MODIS Aqua", persistenceDays: 5 }),
    event({ id: "D", riskLevel: "HIGH", riskScore: 60, state: "", persistenceDays: 4, facility: { name: "Plant" } }),
    event({ id: "E", satellite: "VIIRS S-NPP" }),
  ],
});

test("summarize counts the events the way the dashboard's Overview does", () => {
  const s = summarize(sample());
  assert.equal(s.events, 5);
  assert.equal(s.critical, 2);
  assert.equal(s.high, 2);
  assert.equal(s.atSites, 2);
  assert.equal(s.persistent, 3); // five or more days
  assert.equal(s.states, 2); // Gujarat, Karnataka; the untagged one is not a state
  assert.deepEqual(s.satellites, ["Aqua (MODIS)", "NOAA-20", "S-NPP"]);
  assert.equal(s.observations, null);
});

test("summarize prefers the counts the pipeline wrote into the file", () => {
  const data = sample();
  data.meta = { observations: 6538, persistentSources: 140, statesWithActivity: 29, satellites: ["S-NPP", "Aqua (MODIS)"] };
  const s = summarize(data);
  assert.equal(s.observations, 6538);
  assert.equal(s.persistent, 140);
  assert.equal(s.states, 29);
  assert.deepEqual(s.satellites, ["Aqua (MODIS)", "S-NPP"]);
});

test("summarize copes with a file that has no events", () => {
  const s = summarize({});
  assert.equal(s.events, 0);
  assert.deepEqual(s.satellites, []);
});

test("alerts are the HIGH and CRITICAL events, highest risk first, with the dashboard's wording", () => {
  const alerts = alertsFrom(sample().events);
  assert.deepEqual(alerts.map((a) => a.id), ["A", "B", "C", "D"]);
  assert.equal(alerts[0].title, "Critical thermal activity in Gujarat");
  assert.equal(alerts[2].title, "High thermal activity in Karnataka");
  assert.equal(alerts[3].title, "High thermal activity in an untagged area");
});

test("equal risk keeps the pipeline's own priority order, and missing lists become empty", () => {
  const swapped = sample().events.reverse();
  assert.deepEqual(alertsFrom(swapped).slice(0, 2).map((a) => a.id), ["A", "B"]);
  const [a] = alertsFrom([event({ riskLevel: "HIGH", riskFactors: null, actions: undefined, model: "x" })]);
  assert.deepEqual([a.riskFactors, a.actions, a.reasons, a.model], [[], [], [], null]);
});

test("search matches id, place and classification, ignoring case, and is empty for nothing", () => {
  const alerts = alertsFrom(sample().events);
  assert.deepEqual(matchAlerts(alerts, "karnataka").map((a) => a.id), ["C"]);
  assert.deepEqual(matchAlerts(alerts, " th-1 ").length, 0);
  assert.deepEqual(matchAlerts(alerts, "PERSISTENT industrial").length, 4);
  assert.deepEqual(matchAlerts(alerts, "surat").length, 4);
  assert.deepEqual(matchAlerts(alerts, ""), []);
  assert.deepEqual(matchAlerts(alerts, "   "), []);
});

test("satellite labels", () => {
  assert.equal(satelliteLabel("VIIRS S-NPP"), "S-NPP");
  assert.equal(satelliteLabel("MODIS Terra"), "Terra (MODIS)");
  assert.equal(satelliteLabel("Something new"), "Something new");
});

test("urgency colours follow the risk palette, and unknown urgencies are muted", () => {
  assert.equal(urgencyColor("Now"), "#d03b3b");
  assert.equal(urgencyColor("This week"), "#fab219");
  assert.equal(urgencyColor("Monitor"), "#71808f");
});

test("the update time is shown in India time", () => {
  assert.equal(fmtUpdated("2026-09-25T17:55:30Z"), "2026-09-25 23:25");
  assert.equal(fmtUpdated("2026-09-25T20:00:00Z"), "2026-09-26 01:30"); // past midnight IST
});

test("the age of the data", () => {
  const t = Date.parse("2026-09-25T18:00:00Z");
  assert.equal(fmtAge("2026-09-25T17:30:00Z", t), "under an hour ago");
  assert.equal(fmtAge("2026-09-25T13:00:00Z", t), "5 h ago");
  assert.equal(fmtAge("2026-09-20T18:00:00Z", t), "5 d ago");
  assert.equal(fmtAge("2026-09-26T18:00:00Z", t), "under an hour ago"); // a clock ahead is not negative
});
