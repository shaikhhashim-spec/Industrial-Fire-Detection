/** The sidebar navigation shared by every page — the same eight sections the
 * local dashboard's sidebar has (see app.py NAV_PAGES). Everything here is
 * static and hand-authored (never built from page data), so building the
 * icons directly with the DOM API is safe. */
import { h } from "./dom.mjs";

function svg(...paths) {
  return h("svg", { viewBox: "0 0 24 24", "aria-hidden": "true" }, ...paths);
}
const path = (d) => h("path", { d });
const rect = (x, y, w, ht) => h("rect", { x, y, width: w, height: ht, rx: "1" });

const ICONS = {
  overview: () => svg(rect(3, 3, 7, 18), rect(14, 3, 7, 8), rect(14, 14, 7, 7)),
  map: () => svg(path("M9 4 4 6v14l5-2 6 2 5-2V6l-5 2-6-2Z"), path("M9 4v14M15 6v14")),
  globe: () => svg(h("circle", { cx: 12, cy: 12, r: 9 }), path("M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18")),
  events: () => svg(path("M12 2c0 4-1 7-3 9s-5 3-9 3c4 0 7 1 9 3s3 5 3 9c0-4 1-7 3-9s5-3 9-3c-4 0-7-1-9-3s-3-5-3-9Z")),
  alerts: () => svg(path("M6 16v-5a6 6 0 1 1 12 0v5l2 2H4l2-2zM10 21h4")),
  analytics: () => svg(rect(4, 12, 3, 8), rect(10, 7, 3, 13), rect(16, 3, 3, 17)),
  investigations: () => svg(h("circle", { cx: 10, cy: 10, r: 6 }), path("M20 20l-5.2-5.2")),
  settings: () =>
    svg(
      path("M4 6h9M17 6h3M4 12h4M12 12h8M4 18h11M19 18h1"),
      h("circle", { cx: 15, cy: 6, r: 2 }),
      h("circle", { cx: 8, cy: 12, r: 2 }),
      h("circle", { cx: 17, cy: 18, r: 2 }),
    ),
};

/** href is relative to the site root; every page lives at that root. */
export const NAV = [
  { href: "./", label: "Overview", icon: "overview" },
  { href: "globe/?flat=1&lat=22.5&lon=82.5&z=3.6", label: "Live Map", icon: "map" },
  { href: "globe/", label: "3D Globe", icon: "globe" },
  { href: "events.html", label: "Events", icon: "events" },
  { href: "alerts.html", label: "Alerts", icon: "alerts" },
  { href: "analytics.html", label: "Analytics", icon: "analytics" },
  { href: "investigations.html", label: "Investigations", icon: "investigations" },
  { href: "settings.html", label: "Settings", icon: "settings" },
];

/** Fills `<nav id="nav">` with the section links, marking `activeHref` current.
 * `activeHref` matches a NAV entry's `href` before its query string. */
export function mountNav(activeHref) {
  const el = document.getElementById("nav");
  if (!el) return;
  el.replaceChildren(
    ...NAV.map((item) => {
      const active = item.href.split("?")[0] === activeHref;
      return h(
        "a",
        { class: active ? "navbtn primary" : "navbtn", href: item.href, "aria-current": active ? "page" : null },
        ICONS[item.icon](),
        item.label,
      );
    }),
  );
}
