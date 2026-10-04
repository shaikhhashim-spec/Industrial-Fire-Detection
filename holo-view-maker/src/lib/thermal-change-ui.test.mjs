import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import * as engine from "../../../site/investigations-data.mjs";

const require = createRequire(import.meta.url),
  exports = {};
const code = ts.transpileModule(
  readFileSync(new URL("../components/ThermalChange.tsx", import.meta.url), "utf8"),
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
  require: (id) => (id.endsWith("site/investigations-data.mjs") ? engine : require(id)),
});
const { createElement } = require("react"),
  { renderToStaticMarkup } = require("react-dom/server");

test("globe Thermal Change shows shared results and safe missing-history presentation", () => {
  for (const event of [
    {},
    {
      acqDate: "2026-10-04",
      category: "Requires Verification",
      history: [20, 20, 20, 5].map((frp, i) => ({
        date: `2026-10-0${i + 1}`,
        frp,
        satellite: "VIIRS S-NPP",
        daynight: "N",
      })),
    },
  ]) {
    const result = engine.investigationPriority(event);
    const html = renderToStaticMarkup(createElement(exports.ThermalChange, { event }));
    for (const text of [
      result.thermal.label,
      "Baseline FRP",
      "Current-day peak FRP",
      "Prior comparable days",
      "Days without comparable observations",
      "Priority reasons and limitations",
      "not fire probability",
    ])
      assert.ok(html.includes(text), text);
    if (result.thermal.changePercent < 0) assert.ok(html.includes("-75.0%"));
    assert.doesNotMatch(html, /NaN|undefined|Infinity|confirmed fire/);
  }
});
