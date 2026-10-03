import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

const exports = {};
vm.runInNewContext(
  ts.transpileModule(readFileSync(new URL("./regions.ts", import.meta.url), "utf8"), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  }).outputText,
  { exports },
);

test("planetary presets use the requested oblique camera positions", () => {
  for (const [id, lon, lat, zoom, pitch] of [
    ["middle-east", 48.5, 26.5, 4.8, 35],
    ["india", 82.5, 22.5, 4.2, 25],
    ["north-america", -95, 32, 4.2, 30],
    ["australia", 122, -23, 4.2, 30],
  ]) {
    const preset = exports.regionById(id);
    assert.deepEqual(Array.from(preset.center), [lon, lat]);
    assert.equal(preset.zoom, zoom);
    assert.equal(preset.pitch, pitch);
  }
});

test("corridor centers are valid and remain aligned with dashboard regions", async () => {
  const dashboard = await import("../../../site/regions.mjs");
  for (const preset of exports.REGIONS) {
    assert.equal(exports.inRegion(preset.center[1], preset.center[0], preset.id), true);
    assert.deepEqual(Array.from(preset.bbox), dashboard.regionById(preset.id).bbox);
    assert.equal(preset.label, dashboard.regionById(preset.id).label);
  }
});

test("globe projection and interactive plume handling cannot be replaced by flat URLs", () => {
  const map = readFileSync(new URL("../components/map/GlobeMap.tsx", import.meta.url), "utf8");
  const route = readFileSync(new URL("../routes/index.tsx", import.meta.url), "utf8");
  assert.match(map, /setProjection\(\{ type: "globe" \}\)/);
  assert.doesNotMatch(map, /flatFromUrl|"mercator"/);
  assert.match(map, /"plume-fill"/);
  assert.match(map, /pitch: e\.plume \? 42/);
  assert.doesNotMatch(route, /key=\{region\}|Reload dataset|flatFromUrl/);
});
