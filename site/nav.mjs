/** The sidebar navigation shared by every page — the same sections the
 * local dashboard's sidebar has (see app.py NAV_PAGES). */
import { h } from "./dom.mjs";
import { ICON } from "./icons.mjs";

/** href is relative to the site root; every page lives at that root. */
export const NAV = [
  { href: "./", label: "Overview", icon: "overview" },
  { href: "globe/", label: "3D Globe Model", icon: "globe" },
  { href: "events.html", label: "Events", icon: "events" },
  { href: "alerts.html", label: "Alerts", icon: "bell" },
  { href: "analytics.html", label: "Analytics", icon: "analytics" },
  { href: "investigations.html", label: "Investigations", icon: "search" },
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
        ICON[item.icon](),
        item.label,
      );
    }),
  );
}
