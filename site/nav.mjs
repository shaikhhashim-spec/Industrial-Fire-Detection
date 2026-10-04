/** The sidebar navigation shared by every page — the same sections the
 * local dashboard's sidebar has (see app.py NAV_PAGES). */
import { h } from "./dom.mjs";
import { ICON } from "./icons.mjs";
import { browserPreferences } from "./preferences.mjs";

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

export function navigationHref(href, region) {
  const separator = href.includes("?") ? "&" : "?";
  return `${href}${separator}${new URLSearchParams({ ...(href === "./" ? { view: "overview" } : {}), region })}`;
}

export function updateNavigationRegion(region) {
  const links = document.querySelectorAll("#nav a");
  links.forEach((link, index) => { if (NAV[index]) link.href = navigationHref(NAV[index].href, region); });
  const settings = document.querySelector("#settings-link");
  if (settings) settings.href = `settings.html?${new URLSearchParams({ region })}#alerts`;
}

/** Fills `<nav id="nav">` with the section links, marking `activeHref` current.
 * `activeHref` matches a NAV entry's `href` before its query string. */
export function mountNav(activeHref) {
  const el = document.getElementById("nav");
  if (!el) return;
  const region = new URLSearchParams(location.search).get("region") ?? browserPreferences().region;
  const note = document.querySelector(".side-note");
  if (note) note.textContent = "NASA FIRMS observations. Human verification required. Personal reviews stay in this browser.";
  el.replaceChildren(
    ...NAV.map((item) => {
      const active = item.href.split("?")[0] === activeHref;
      return h(
        "a",
        { class: active ? "navbtn primary" : "navbtn", href: navigationHref(item.href, region), "aria-current": active ? "page" : null },
        ICON[item.icon](),
        item.label,
      );
    }),
  );
}
