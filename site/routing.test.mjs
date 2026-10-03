import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { NAV } from "./nav.mjs";
import { globeRedirectTarget, redirectRootToGlobe } from "./routing.mjs";

test("Overview remains the default, including unrelated query and hash context", () => {
  for (const suffix of ["", "#overview", "?search=steel#events"]) {
    assert.equal(globeRedirectTarget(`https://example.org/project/${suffix}`), null);
  }
});

test("all explicit region deep links preserve their query and hash under globe/", () => {
  for (const root of ["https://example.org/", "https://example.org/project/", "https://example.org/project/index.html"]) {
    for (const region of ["global", "india", "middle-east", "unknown", ""]) {
      const suffix = `?region=${region}&event=a%20b&event=c&lat=22.5&lon=82.5&z=3.6#hotspot`;
      const target = new URL(globeRedirectTarget(root + suffix));
      assert.equal(target.pathname, new URL("globe/", root).pathname);
      assert.equal(target.search + target.hash, suffix);
    }
  }
});

test("legacy flat links enter the globe with every flat parameter removed", () => {
  for (const query of ["flat=1", "region=global&flat=1", "flat=0&region=india&flat=1"]) {
    const target = new URL(globeRedirectTarget(`https://example.org/project/?${query}&lat=22.5&event=a%20b#source`));
    assert.equal(target.pathname, "/project/globe/");
    assert.equal(target.searchParams.has("flat"), false);
    assert.equal(target.searchParams.get("lat"), "22.5");
    assert.equal(target.searchParams.get("event"), "a b");
    assert.equal(target.hash, "#source");
  }
});

test("redirect replaces legacy history and gates Overview initialization", () => {
  const replacements = [];
  const location = { href: "https://example.org/project/?region=global#event", replace: (href) => replacements.push(href) };
  assert.equal(redirectRootToGlobe(location), true);
  assert.deepEqual(replacements, ["https://example.org/project/globe/?region=global#event"]);
  location.href = "https://example.org/project/";
  assert.equal(redirectRootToGlobe(location), false);
  assert.equal(replacements.length, 1);
  const html = readFileSync(new URL("./index.html", import.meta.url), "utf8");
  assert.match(html, /if \(!redirectRootToGlobe\(window\.location\)\)\s*\{\s*import\("\.\/dashboard\.js"\)/);
  assert.doesNotMatch(html, /src="dashboard\.js"/);
});

test("public navigation offers one premier globe entry and no flat destination", () => {
  assert.deepEqual(NAV.slice(0, 2).map(({ label }) => label), ["Overview", "3D Globe Model"]);
  assert.equal(NAV.filter(({ href }) => href.startsWith("globe/")).length, 1);
  assert.equal(NAV.some(({ href, label }) => href.includes("flat=") || label === "Live Map"), false);
});
