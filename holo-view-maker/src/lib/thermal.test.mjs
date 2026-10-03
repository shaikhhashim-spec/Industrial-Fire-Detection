import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

const code = ts.transpileModule(readFileSync(new URL("./thermal.ts", import.meta.url), "utf8"), {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText;

function event(id, date, overrides = {}) {
  return {
    id,
    acqDate: date,
    latitude: 22.5,
    longitude: 82.5,
    riskScore: 60,
    frp: 20,
    riskLevel: "HIGH",
    category: "Requires Verification",
    ...overrides,
  };
}

async function load(national, global) {
  const exports = {};
  vm.runInNewContext(code, {
    exports,
    console,
    require: () => ({ assetUrl: (path) => path }),
    fetch: async (path) => {
      const payload = path.endsWith("global-events.json") ? global : national;
      return { ok: !!payload, json: async () => payload };
    },
  });
  return exports.fetchThermalEvents();
}

function feed(events, scope = "india", source = "firms_live") {
  return {
    events,
    meta: {
      scope,
      source,
      generatedAt: "2026-10-03T00:00:00Z",
      events: events.length,
      windowDays: 1,
      attribution: ["NASA FIRMS"],
    },
  };
}

test("missing global feed preserves India evidence and rejects invalid coordinates", async () => {
  const result = await load(
    feed([event("india", "2026-10-03"), event("bad", "2026-10-03", { latitude: 100 })]),
    null,
  );
  assert.equal(result.events.length, 1);
  assert.equal(result.events[0].id, "india");
  assert.equal(result.meta.scope, "india");
});

test("same-date national dossier wins, but a newer worldwide observation replaces stale evidence", async () => {
  const national = feed([event("india", "2026-10-02", { facility: { name: "Plant" } })]);
  const same = await load(national, feed([event("global", "2026-10-02")], "global"));
  assert.equal(same.events.length, 1);
  assert.equal(same.events[0].facility.name, "Plant");
  const newer = await load(national, feed([event("global", "2026-10-03")], "global"));
  assert.equal(newer.events.length, 1);
  assert.equal(newer.events[0].id, "global");
  assert.equal(newer.meta.datasets.length, 2);
});

test("partial sensor export and a valid empty worldwide feed retain honest provenance", async () => {
  const global = feed([], "global", "mixed");
  global.meta.partial = true;
  const result = await load(null, global);
  assert.equal(result.source, "live");
  assert.equal(result.events.length, 0);
  assert.equal(result.meta.partial, true);
  assert.equal(result.meta.scope, "global");
});

test("same-day later observation wins consistently with investigations", async () => {
  const result = await load(
    feed([event("india", "2026-10-03", { evidence: { lastSeen: "2026-10-03T01:00:00Z" } })]),
    feed(
      [event("global", "2026-10-03", { evidence: { lastSeen: "2026-10-03T02:00:00Z" } })],
      "global",
    ),
  );
  assert.equal(result.events[0].id, "global");
});
