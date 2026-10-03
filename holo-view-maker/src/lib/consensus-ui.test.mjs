import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import * as engine from "../../../site/consensus.mjs";

const require = createRequire(import.meta.url);
const exports = {};
const code = ts.transpileModule(
  readFileSync(new URL("../components/ConsensusArena.tsx", import.meta.url), "utf8"),
  {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.CommonJS,
      jsx: ts.JsxEmit.ReactJSX,
    },
  },
).outputText;
vm.runInNewContext(code, {
  exports,
  require: (id) => (id.endsWith("site/consensus.mjs") ? engine : require(id)),
});
const { createElement } = require("react");
const { renderToStaticMarkup } = require("react-dom/server");

test("globe Arena renders the same rule-based index and all evidence roles", () => {
  const event = {
    latitude: 20,
    longitude: 70,
    frp: 80,
    confidence: 90,
    persistenceDays: 3,
    detectionCount: 8,
    satellite: "VIIRS S-NPP",
  };
  const result = engine.evaluateConsensus(event);
  const html = renderToStaticMarkup(createElement(exports.ConsensusArena, { event }));
  assert.ok(html.includes(`${result.index}/100`));
  for (const text of [
    "Sentinel",
    "Skeptic",
    "Arbiter",
    "Rule-based evidence screening",
    "Verification required",
    "Evidence debate",
  ])
    assert.ok(html.includes(text), text);
  assert.ok(html.includes(`aria-valuenow="${result.index}"`));
  assert.doesNotMatch(html, /CONFIRMED INDUSTRIAL|glint probability|99th percentile|NaN|undefined/);
});

test("missing evidence renders safely without manufacturing confidence", () => {
  const html = renderToStaticMarkup(createElement(exports.ConsensusArena, { event: {} }));
  assert.ok(html.includes('aria-valuenow="0"'));
  assert.ok(html.includes("unavailable"));
  assert.doesNotMatch(html, /NaN|undefined/);
});
