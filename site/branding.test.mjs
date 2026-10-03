import assert from "node:assert/strict";
import { test } from "node:test";
import { applyRegionBranding, regionBranding } from "./branding.mjs";
import { REGIONS } from "./regions.mjs";
import { renderBranding } from "./page.mjs";

test("global and India have exact geographic branding and search context", () => {
  assert.equal(regionBranding("global").subtitle, "Planetary satellite thermal monitoring and global industrial fire risk analysis.");
  assert.equal(regionBranding("india").subtitle, "Satellite thermal monitoring and industrial risk analysis for India.");
  assert.equal(regionBranding("global").search, "Search event ID, country, region");
  assert.equal(regionBranding("india").search, "Search event ID, state, district");
});

test("every other geographic window uses its own name", () => {
  for (const region of REGIONS.filter(({ id }) => !["global", "india"].includes(id))) {
    const brand = regionBranding(region.id);
    assert.equal(brand.subtitle, `Satellite thermal monitoring and industrial risk analysis for ${region.label}.`);
    assert.ok(brand.sidebar.endsWith(region.label));
    assert.equal(brand.search, region.id === "jharkhand-odisha" ? "Search event ID, state, district" : "Search event ID, country, region");
  }
});

test("unknown geography uses the existing India fallback", () => {
  assert.deepEqual(regionBranding("unknown"), regionBranding("india"));
});

test("application accepts region objects and changes scope without a DOM dependency", () => {
  assert.equal(renderBranding, applyRegionBranding);
  assert.deepEqual(applyRegionBranding(REGIONS[0]), regionBranding("global"));
  const nodes = new Map([".topbar-brand .sub", ".brand-sub", "#search"].map((selector) => [selector, {
    setAttribute(name, value) { this[name] = value; },
  }]));
  const document = { querySelector: (selector) => nodes.get(selector) };
  for (const id of ["global", "india", "europe"]) {
    const brand = applyRegionBranding(REGIONS.find((region) => region.id === id), document);
    assert.equal(nodes.get(".topbar-brand .sub").textContent, brand.subtitle);
    assert.equal(nodes.get(".brand-sub").textContent, brand.sidebar);
    assert.equal(nodes.get("#search").placeholder, brand.search);
    assert.equal(nodes.get("#search")["aria-label"], brand.search);
  }
  assert.deepEqual(applyRegionBranding("global", { querySelector: () => null }), regionBranding("global"));
});
