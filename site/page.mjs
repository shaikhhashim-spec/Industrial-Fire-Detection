/*
 * What every page on the site does the same way: fetch the live data, show
 * where it came from and how old it is in the topbar, and fail the same way
 * if the fetch does not work.
 */
import { h } from "./dom.mjs";
import { fmtAge, fmtUpdated } from "./overview.mjs";

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
  el.replaceChildren(
    stored ? "Stored live run" : "Live NASA FIRMS",
    h("br"),
    "Updated ",
    h("span", { class: "v", title: meta.generatedAt }, meta.generatedAt ? `${fmtUpdated(meta.generatedAt)} IST` : "never"),
    meta.generatedAt && h("br"),
    meta.generatedAt && fmtAge(meta.generatedAt),
  );
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
    renderMeta(data.meta ?? {});
    await main(data);
  } catch (err) {
    console.warn("Could not read the live data:", err);
    renderLoadError(container);
  }
}
