import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

// Resolve Vite's alias for the production TypeScript without a second test bundler.
const require = createRequire(import.meta.url);
const source = readFileSync(new URL("./geo-layers.ts", import.meta.url), "utf8");
const code = ts.transpileModule(source, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText;
const exports = {};
vm.runInNewContext(code, {
  exports,
  require: (id) =>
    id === "@/lib/thermal"
      ? { RISK_COLORS: { HIGH: "#ec835a" }, CATEGORY_COLORS: {} }
      : id.startsWith("@/")
        ? {}
        : require(id),
});
const { compass16, plumesToGeoJSON, unwrapPlumeRing } = exports;

test("compass uses all sixteen sectors and wraps negative/large bearings", () => {
  const headings = [
    "N",
    "NNE",
    "NE",
    "ENE",
    "E",
    "ESE",
    "SE",
    "SSE",
    "S",
    "SSW",
    "SW",
    "WSW",
    "W",
    "WNW",
    "NW",
    "NNW",
  ];
  headings.forEach((heading, i) => assert.equal(compass16(i * 22.5), heading));
  assert.equal(compass16(-90), "W");
  assert.equal(compass16(720), "N");
  assert.equal(compass16(359), "N");
  assert.equal(compass16(11.25), "NNE");
});

test("eastward and westward dateline rings remain local and closed", () => {
  for (const sign of [1, -1]) {
    const ring = unwrapPlumeRing([
      [179.99 * sign, 0],
      [-179.98 * sign, 0.02],
      [-179.97 * sign, -0.02],
    ]);
    assert.equal(ring.length, 4);
    assert.equal(ring[0][0], ring[3][0]);
    for (let i = 1; i < ring.length; i++) assert.ok(Math.abs(ring[i][0] - ring[i - 1][0]) < 1);
  }
});

test("GeoJSON carries tactical metrics and drops invalid rings", () => {
  const event = {
    id: "global-1",
    frp: 40,
    riskLevel: "HIGH",
    region: "Pacific",
    plume: {
      polygon: [
        [179.99, 0],
        [-179.99, 0.01],
        [-179.99, -0.01],
        [179.99, 0],
      ],
      windSpeedKmh: 30,
      downwindBearingDeg: 90,
      coneLengthKm: 6,
    },
  };
  const result = plumesToGeoJSON([
    event,
    { ...event, plume: undefined },
    {
      ...event,
      plume: {
        ...event.plume,
        polygon: [
          [NaN, 0],
          [0, 0],
          [1, 0],
        ],
      },
    },
  ]);
  assert.equal(result.features.length, 1);
  const feature = result.features[0];
  assert.equal(feature.geometry.type, "Polygon");
  assert.deepEqual(JSON.parse(JSON.stringify(feature.properties)), {
    id: "global-1",
    frp: 40,
    riskLevel: "HIGH",
    riskColor: "#ec835a",
    windSpeedKmh: 30,
    downwindBearingDeg: 90,
    coneLengthKm: 6,
    region: "Pacific",
  });
});
