/*
 * The public Events table: every detected event, in the same columns and
 * order as the dashboard's Events page (app.py EVENT_COLUMN_LABELS /
 * _readable_event_columns), with the open-source context (facility, nearest
 * place, why it is here) flattened to text the way the dashboard's own CSV
 * export reads.
 */

import { matchesSearch } from "./search.mjs";

const int = (v) => Math.round(v).toLocaleString("en-US");
const mw = (v) => v.toFixed(1);
const coord = (v) => v.toFixed(4);

export const COLUMNS = [
  { key: "id", label: "Event" },
  { key: "country", label: "Country" },
  { key: "region", label: "Region" },
  { key: "state", label: "State" },
  { key: "district", label: "District" },
  { key: "place", label: "Nearest place" },
  { key: "category", label: "Category" },
  { key: "riskLevel", label: "Risk" },
  { key: "riskScore", label: "Risk score", numeric: true, format: int },
  { key: "frp", label: "Peak FRP (MW)", numeric: true, format: mw },
  { key: "persistenceDays", label: "Days active", numeric: true, format: int },
  { key: "detectionCount", label: "Detections", numeric: true, format: int },
  { key: "corroborated", label: "Corroborated" },
  { key: "facility", label: "Nearest facility" },
  { key: "reasons", label: "Why it is here" },
  { key: "latitude", label: "Latitude", numeric: true, format: coord },
  { key: "longitude", label: "Longitude", numeric: true, format: coord },
];

/** The text a table cell shows for one row's value in this column. */
export function formatCell(col, value) {
  if (value == null) return "";
  return col.format ? col.format(value) : String(value);
}

function formatPlace(place) {
  if (!place || typeof place !== "object" || !place.name) return "";
  if (typeof place.distanceKm === "number" && place.distanceKm >= 1) {
    return `${place.direction ?? ""} ${Math.round(place.distanceKm)} km of ${place.name}`.trim();
  }
  return place.name;
}

function formatFacility(facility) {
  if (!facility || typeof facility !== "object") return "";
  const head = [facility.name || "unnamed", facility.kind].filter(Boolean).join(": ");
  return `${head}, ${facility.distanceKm} km (${facility.source})`;
}

/** One event to one table row — every value already the plain text or number
 * the table displays, so sorting and search need no per-column special case. */
export function toRow(event) {
  return {
    id: event.id,
    country: event.country ?? "",
    region: event.region ?? "",
    state: event.state ?? "",
    district: event.district ?? "",
    place: formatPlace(event.place),
    category: event.category ?? "",
    riskLevel: event.riskLevel,
    riskScore: event.riskScore ?? 0,
    frp: event.frp ?? 0,
    persistenceDays: event.persistenceDays ?? 0,
    detectionCount: event.detectionCount ?? 0,
    corroborated: event.corroborated === true ? "Yes" : event.corroborated === false ? "No" : "Unknown",
    facility: formatFacility(event.facility),
    reasons: Array.isArray(event.reasons) ? event.reasons.join(" ") : "",
    latitude: event.latitude,
    longitude: event.longitude,
  };
}

export function toRows(events) {
  return (events ?? []).map(toRow);
}

/** Every row whose event id, place or classification contains the query.
 * All rows for an empty query — this is a live filter, not a search-results
 * toggle like the Overview/Alerts search. */
export function filterEventRows(rows, query, filters = {}) {
  const q = query.trim().toLowerCase();
  if (!q && !filters.risk && !filters.category && !filters.minDays) return rows;
  return rows.filter((r) =>
    matchesSearch([r.id, r.country, r.region, r.state, r.district, r.category, r.riskLevel, r.place, r.facility], q) &&
    (!filters.risk || r.riskLevel === filters.risk) && (!filters.category || r.category === filters.category) &&
    (!filters.minDays || r.persistenceDays >= Number(filters.minDays)),
  );
}

export function sortRows(rows, key, dir = "desc") {
  const sign = dir === "asc" ? 1 : -1;
  const numeric = COLUMNS.find((c) => c.key === key)?.numeric ?? false;
  return [...rows].sort((a, b) => {
    if (numeric) return sign * ((a[key] ?? -Infinity) - (b[key] ?? -Infinity));
    return sign * String(a[key] ?? "").localeCompare(String(b[key] ?? ""));
  });
}

/** A CSV of exactly what the table shows, one column per header, RFC-4180
 * quoting — matching the dashboard's own "Export CSV" download. */
export function toCsv(rows) {
  const esc = (v) => {
    let s = String(v ?? "");
    if (/^[\s\u0000-\u001f]*[=+@-]/.test(s) || /^[\t\r\n]/.test(s)) s = `'${s}`;
    return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const header = COLUMNS.map((c) => esc(c.label)).join(",");
  const lines = rows.map((r) => COLUMNS.map((c) => esc(r[c.key])).join(","));
  return [header, ...lines].join("\r\n");
}
