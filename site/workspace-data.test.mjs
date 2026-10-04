import assert from "node:assert/strict";
import { test } from "node:test";
import { loadWorkspace, scopedWorkspace } from "./workspace-data.mjs";
import { normalizePreferences, readPreferences, savePreferences } from "./preferences.mjs";
import { navigationHref } from "./nav.mjs";
import { globeRedirectTarget } from "./routing.mjs";
import { regionById } from "./regions.mjs";
import { filterEventRows } from "./events.mjs";

const payload = (scope) => ({ meta: { scope, source: "local_cache", observations: 999 }, events: [
  { id: "IND", latitude: 22, longitude: 85, acqDate: "2026-10-03" },
  { id: "BRA", latitude: -10, longitude: -55, acqDate: "2026-10-02" },
] });

test("either working feed keeps the public workspace available", async () => {
  for (const missing of ["india", "global"]) {
    const workspace = await loadWorkspace(async (url) => {
      const scope = url.includes("global-") ? "global" : "india";
      return { ok: scope !== missing, status: 503, json: async () => payload(scope) };
    });
    const scoped = scopedWorkspace(workspace, regionById(missing));
    assert.equal(workspace.failures.length, 1);
    assert.match(scoped.coverage, /requested feed unavailable/);
    assert.equal(scoped.data.meta.observations, undefined);
    assert.equal(scoped.data.meta.observationEnd, "2026-10-03");
  }
  await assert.rejects(loadWorkspace(async () => ({ ok: false, status: 503 })), /No published snapshots/);
});

test("India prefers its richer national evidence; other geographic windows use global data", () => {
  const workspace = { feeds: { india: payload("india"), global: payload("global") } };
  assert.equal(scopedWorkspace(workspace, regionById("india")).data.events.length, 1);
  assert.equal(scopedWorkspace(workspace, regionById("south-america")).data.events[0].id, "BRA");
});

test("personal preferences validate values and tolerate blocked browser storage", () => {
  assert.deepEqual(normalizePreferences({ region: "invalid", pageSize: 999, autoReload: "true" }), { region: "global", pageSize: 100, autoReload: false });
  assert.equal(readPreferences({ getItem() { throw new Error("blocked"); } }).region, "global");
  assert.equal(savePreferences(null, {}).ok, false);
  let saved;
  assert.equal(savePreferences({ setItem(key, value) { saved = value; } }, { region: "india", pageSize: 50 }).ok, true);
  assert.equal(JSON.parse(saved).pageSize, 50);
});

test("Overview navigation retains scope without accidentally entering the globe", () => {
  const href = navigationHref("./", "global");
  assert.equal(globeRedirectTarget(new URL(href, "https://example.org/project/").href), null);
  assert.equal(navigationHref("events.html", "global"), "events.html?region=global");
});

test("event search combines risk, category and duration filters", () => {
  const rows = [{ id: "A", riskLevel: "HIGH", category: "Industrial", persistenceDays: 5 },
    { id: "B", riskLevel: "LOW", category: "Industrial", persistenceDays: 1 }];
  assert.deepEqual(filterEventRows(rows, "industrial", { risk: "HIGH", minDays: "2" }).map((r) => r.id), ["A"]);
});
