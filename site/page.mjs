/*
 * What every page on the site does the same way: fetch the live data, show
 * where it came from and how old it is in the topbar, and fail the same way
 * if the fetch does not work.
 */
import { h } from "./dom.mjs";
import { fmtAge, fmtUpdated } from "./overview.mjs";
import { applyRegionBranding } from "./branding.mjs";
import { REGIONS, regionById } from "./regions.mjs";
import { loadWorkspace, scopedWorkspace } from "./workspace-data.mjs";
import { browserPreferences } from "./preferences.mjs";
import { updateNavigationRegion } from "./nav.mjs";

export { applyRegionBranding as renderBranding } from "./branding.mjs";

export const DATA_URL = "globe/data/events.json";

export async function loadData(url = DATA_URL) {
  const res = await fetch(url, { cache: "no-cache" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

/** Fills `#meta` with the same "source / updated / age" block every page shows. */
export function renderMeta(meta) {
  const el = document.querySelector("#meta");
  if (!el) return;
  const stored = meta.source && meta.source !== "firms_live" && meta.source !== "mixed";
  el.replaceChildren(...[
    stored ? "NASA FIRMS (cached pull)" : meta.source === "mixed" ? "NASA FIRMS (live + cached pull)" : meta.source === "firms_live" ? "NASA FIRMS (live pull)" : "Source unavailable",
    h("br"),
    "Exported ",
    h("span", { class: "v", title: meta.generatedAt }, meta.generatedAt ? `${fmtUpdated(meta.generatedAt)} IST` : "never"),
    meta.generatedAt && h("br"),
    meta.generatedAt && fmtAge(meta.generatedAt),
    meta.observationEnd && h("br"),
    meta.observationEnd && `Last observed ${meta.observationEnd}`,
  ].filter((child) => child != null && child !== false));
}

/** The one shape every page's load() falls back to when the fetch fails. */
export function renderLoadError(container) {
  container.replaceChildren(
    h("p", { class: "loading" }, "The live data could not be loaded. "),
    h("button", { class: "btn", type: "button", onclick: () => location.reload() }, "Reload"),
  );
}

/** Runs `main(data)` once the live data loads, in the given container's place
 * on error. Every page's entry point is exactly this one call. */
export async function boot(main, containerSelector = "#content") {
  const container = document.querySelector(containerSelector);
  try {
    const data = await loadData();
    const region = data.meta?.scope === "global" ? "global" : "india";
    applyRegionBranding(region);
    const fixedRegion = document.querySelector(".topbar span.select[aria-label='Region']");
    if (fixedRegion) fixedRegion.textContent = region === "global" ? "Global" : "India";
    const dates = (data.events ?? []).map((event) => event.acqDate).filter((date) => /^\d{4}-\d{2}-\d{2}$/.test(date ?? "")).sort();
    renderMeta({ ...data.meta, observationEnd: data.meta?.observationEnd ?? dates.at(-1) });
    await main(data);
  } catch (err) {
    console.warn("Could not read the live data:", err);
    renderLoadError(container);
  }
}

export async function bootWorkspace(main, containerSelector = "#content") {
  const container = document.querySelector(containerSelector);
  try {
    const workspace = await loadWorkspace();
    let selector = document.querySelector("#region");
    if (!selector) {
      const fixed = document.querySelector(".topbar span.select[aria-label='Region']");
      selector = h("select", { id: "region", class: "select", "aria-label": "Region" });
      fixed?.replaceWith(selector);
    }
    selector.replaceChildren(...REGIONS.map((region) => h("option", { value: region.id }, region.label)));
    const preferences = browserPreferences();
    selector.value = regionById(new URLSearchParams(location.search).get("region") ?? preferences.region).id;
    const render = () => {
      const region = regionById(selector.value);
      const { data, coverage } = scopedWorkspace(workspace, region);
      const url = new URL(location.href);
      url.searchParams.set("region", region.id);
      if (url.pathname.endsWith("/") || url.pathname.endsWith("index.html")) url.searchParams.set("view", "overview");
      history.replaceState(null, "", url);
      applyRegionBranding(region);
      updateNavigationRegion(region.id);
      renderMeta(data.meta);
      main(data, region, coverage);
      if (!container.querySelector(".scope-note")) container.prepend(h("p", { class: "scope-note", role: "status" }, `${region.label} / ${coverage}. Satellite detections require verification.`));
    };
    selector.onchange = render;
    render();
    if (preferences.autoReload) setInterval(() => location.reload(), 5 * 60 * 1000);
  } catch (error) {
    console.warn("Could not load workspace snapshots:", error);
    renderLoadError(container);
  }
}
