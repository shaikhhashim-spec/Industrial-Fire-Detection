import assert from "node:assert/strict";
import { test } from "node:test";
import { alertCard, explainer } from "./alerts-view.mjs";
import { alertsFrom } from "./overview.mjs";

// Minimal DOM implements the operations used by the site's shared h() builder.
class Node {
  constructor(tag = "", text = "") { this.tag = tag; this.text = text; this.children = []; this.attrs = {}; this.listeners = {}; }
  setAttribute(key, value) { this.attrs[key] = String(value); }
  append(...nodes) { for (const node of nodes) { node.parent = this; this.children.push(node); } }
  addEventListener(key, fn) { this.listeners[key] = fn; }
  get textContent() { return this.text + this.children.map((n) => n.textContent).join(" "); }
  querySelector(selector) {
    const matches = (n) => selector.startsWith("[") ? Object.hasOwn(n.attrs, selector.slice(1, -1))
      : selector.startsWith(".") ? (n.attrs.class ?? "").split(" ").includes(selector.slice(1)) : n.tag === selector;
    for (const child of this.children) {
      if (matches(child)) return child;
      const found = child.querySelector(selector); if (found) return found;
    }
    return null;
  }
  replaceWith(node) { const index = this.parent.children.indexOf(this); node.parent = this.parent; this.parent.children[index] = node; }
}
const document = {
  createElement: (tag) => new Node(tag), createElementNS: (_, tag) => new Node(tag),
  createTextNode: (text) => new Node("", text),
};
const makeAlert = (over = {}) => alertsFrom([{ id: "X", riskLevel: "CRITICAL", riskScore: 90,
  latitude: 20, longitude: 73, frp: 80, confidence: 90, persistenceDays: 3,
  country: "India", riskFactors: [], actions: [], ...over }])[0];

test("public card carries verdict, index, severity hook, named location and valid wind badge", () => {
  globalThis.document = document;
  const [card] = alertCard(makeAlert({ plume: { windSpeedKmh: 15, coneLengthKm: 8, downwindBearingDeg: 270, source: "cached" } }));
  assert.equal(card.attrs["data-severity"], "CRITICAL");
  assert.match(card.textContent, /Verification required.*\/100 index/);
  assert.match(card.textContent, /Location India/);
  assert.match(card.textContent, /Plume 8.0 km \(W\)/);
  assert.match(card.querySelector(".plume-badge").textContent, /Estimated plume W 8.0 km.*cached\/unverified.*15 km\/h wind/);
});

test("invalid coordinates or plume omit badge and unavailable numbers render safely", () => {
  globalThis.document = document;
  const [card] = alertCard(makeAlert({ latitude: null, longitude: NaN, country: null, frp: NaN,
    plume: { windSpeedKmh: 15, coneLengthKm: 8, downwindBearingDeg: 0 } }));
  assert.equal(card.querySelector(".plume-badge"), null);
  assert.match(card.textContent, /Location unavailable/);
  assert.doesNotMatch(card.textContent, /NaN|Infinity/);
});

test("lazy explainer opens once and contains independently expandable Arena roles and limitations", () => {
  globalThis.document = document;
  const [, details] = alertCard(makeAlert());
  assert.ok(details.querySelector("[data-lazy]"));
  details.listeners.toggle();
  assert.ok(details.querySelector("[data-lazy]"));
  details.open = true;
  details.listeners.toggle();
  assert.equal(details.querySelector("[data-lazy]"), null);
  const panel = details.querySelector(".consensus-panel");
  assert.equal(panel.tag, "details");
  assert.match(panel.querySelector("summary").textContent, /Multi-Agent Arena/);
  assert.match(panel.textContent, /Rule-based evidence screening.*no LLMs/);
  for (const role of ["Sentinel", "Skeptic", "Arbiter"]) assert.match(panel.textContent, new RegExp(role));
  assert.match(panel.querySelector(".consensus-limitations").textContent, /not probability or a confirmed fire/);
  assert.match(panel.textContent, /Cloud cover unavailable/);
  details.listeners.toggle();
  assert.equal(details.querySelector(".consensus-panel"), panel);
});

test("model note warns correctness cannot be validated and handles nonfinite confidence", () => {
  globalThis.document = document;
  const body = explainer(makeAlert({ model: { label: "Fire", confidence: Infinity, agrees: true } }));
  assert.match(body.textContent, /Model confidence cannot validate correctness/);
  assert.doesNotMatch(body.textContent, /Infinity|NaN/);
});

test("evidence reasons append as individual nodes, not stringified DOM arrays", () => {
  globalThis.document = document;
  const body = explainer(makeAlert({ reasons: ["Repeated night observations", "Facility proximity is context"] }));
  assert.match(body.textContent, /Repeated night observations/);
  assert.match(body.textContent, /Facility proximity is context/);
  assert.doesNotMatch(body.textContent, /object HTML/);
});
