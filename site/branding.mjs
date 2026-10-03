import { regionById } from "./regions.mjs";

/** Branding follows the displayed geographic window, not the URL alone. */
export function regionBranding(region) {
  const resolved = regionById(typeof region === "string" ? region : region?.id);
  const india = resolved.id === "india";
  return {
    subtitle: resolved.id === "global"
      ? "Planetary satellite thermal monitoring and global industrial fire risk analysis."
      : `Satellite thermal monitoring and industrial risk analysis for ${india ? "India" : resolved.label}.`,
    sidebar: resolved.id === "global" ? "Planetary thermal monitoring" : `Satellite thermal monitoring for ${india ? "India" : resolved.label}`,
    search: india || resolved.id === "jharkhand-odisha"
      ? "Search event ID, state, district"
      : "Search event ID, country, region",
  };
}

export function applyRegionBranding(region, document = globalThis.document) {
  const brand = regionBranding(region);
  if (!document) return brand;
  const subtitle = document.querySelector(".topbar-brand .sub");
  const sidebar = document.querySelector(".brand-sub");
  const search = document.querySelector("#search");
  if (subtitle) subtitle.textContent = brand.subtitle;
  if (sidebar) sidebar.textContent = brand.sidebar;
  if (search) {
    search.placeholder = brand.search;
    search.setAttribute("aria-label", brand.search);
  }
  return brand;
}
