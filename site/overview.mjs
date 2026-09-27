/*
 * The numbers and alerts on the public Overview page, worked out from the same
 * events.json the 3D globe reads. Pure functions, so they can be tested with
 * `node --test "site/*.test.mjs"` and produce the same figures as the dashboard's Overview.
 */

export const RISK_COLORS = { LOW: "#0ca30c", MODERATE: "#fab219", HIGH: "#ec835a", CRITICAL: "#d03b3b" };
export const PERSISTENT_COLOR = "#fab219";
export const ACCENT = "#5cb8dc";
export const MUTED = "#71808f";
// Single-series charts (a bar chart ranking states, satellites, FRP bins): the
// accent above is reserved for actions and selection, so those charts reuse
// this hue instead — the same one the dashboard's own charts use.
export const SERIES = "#3987e5";

// Fixed order, shared with the dashboard (app.py) and the globe
// (holo-view-maker/src/lib/thermal.ts) — never reassigned or cycled.
export const CATEGORY_COLORS = {
  "Likely Industrial Fire": "#3987e5",
  "Persistent Non-Industrial Thermal Source": "#d95926",
  "Transient Industrial Flare": "#199e70",
  "Likely Agricultural Burning": "#c98500",
  "Sun Glint / False Positive": "#d55181",
  "Likely Wildfire": "#008300",
  "Persistent Industrial Activity": "#9085e9",
  "Requires Verification": "#e66767",
};

// The dashboard counts a source as persistent from this many distinct days
// (config.NATIONAL_PERSISTENCE_MIN_DAYS_HISTORY). Only used when the data file
// predates meta.persistentSources.
const PERSISTENT_MIN_DAYS = 5;

const SATELLITE_LABELS = {
  "VIIRS S-NPP": "S-NPP",
  "VIIRS NOAA-20": "NOAA-20",
  "VIIRS NOAA-21": "NOAA-21",
  "MODIS Aqua": "Aqua (MODIS)",
  "MODIS Terra": "Terra (MODIS)",
};

export function satelliteLabel(name) {
  return SATELLITE_LABELS[name] ?? name;
}

/** The four tiles and the line under them. Prefers the counts the pipeline wrote
 * into the file (they come from the raw observations, which the file does not
 * carry) and falls back to counting the events. */
export function summarize(data) {
  const events = data.events ?? [];
  const meta = data.meta ?? {};
  const states = new Set(events.map((e) => e.state).filter(Boolean));
  const satellites = new Set(events.map((e) => satelliteLabel(e.satellite)).filter(Boolean));
  return {
    observations: meta.observations ?? null,
    events: events.length,
    persistent:
      meta.persistentSources ?? events.filter((e) => e.persistenceDays >= PERSISTENT_MIN_DAYS).length,
    atSites: events.filter((e) => e.facility).length,
    critical: events.filter((e) => e.riskLevel === "CRITICAL").length,
    high: events.filter((e) => e.riskLevel === "HIGH").length,
    states: meta.statesWithActivity ?? states.size,
    satellites: [...(meta.satellites ?? satellites)].sort(),
  };
}

function titleCase(word) {
  return word.charAt(0) + word.slice(1).toLowerCase();
}

/** Every HIGH and CRITICAL event, highest risk first, worded as the dashboard words it. */
export function alertsFrom(events) {
  return (events ?? [])
    .filter((e) => e.riskLevel === "HIGH" || e.riskLevel === "CRITICAL")
    .sort(
      (a, b) =>
        b.riskScore - a.riskScore ||
        (a.priority ?? Infinity) - (b.priority ?? Infinity) ||
        String(a.id).localeCompare(String(b.id)),
    )
    .map((e) => ({
      id: e.id,
      title: `${titleCase(e.riskLevel)} thermal activity in ${e.state || "an untagged area"}`,
      severity: e.riskLevel,
      riskScore: e.riskScore,
      priority: typeof e.priority === "number" ? e.priority : null,
      latitude: e.latitude,
      longitude: e.longitude,
      days: e.persistenceDays ?? 0,
      frp: e.frp ?? 0,
      classification: e.category || "Thermal event",
      region: e.region ?? "",
      state: e.state ?? "",
      district: e.district ?? "",
      riskSummary: e.riskSummary ?? null,
      riskFactors: Array.isArray(e.riskFactors) ? e.riskFactors : [],
      actions: Array.isArray(e.actions) ? e.actions : [],
      model: e.model && typeof e.model === "object" ? e.model : null,
      reasons: Array.isArray(e.reasons) ? e.reasons : [],
    }));
}

/** Alerts whose id, place or classification contains the query. Nothing for an empty query. */
export function matchAlerts(alerts, query) {
  const q = query.trim().toLowerCase();
  if (!q) return [];
  return alerts.filter((a) =>
    [a.id, a.region, a.state, a.district, a.classification].some((v) => String(v).toLowerCase().includes(q)),
  );
}

export function urgencyColor(urgency) {
  return { Now: RISK_COLORS.CRITICAL, Today: RISK_COLORS.HIGH, "This week": RISK_COLORS.MODERATE }[urgency] ?? MUTED;
}

/** "2026-09-25 23:25" in India time, the zone the dashboard's own clock shows. */
export function fmtUpdated(iso) {
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Kolkata",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(new Date(iso))
      .map((p) => [p.type, p.value]),
  );
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}`;
}

/** How old the data is, because a static page cannot refresh itself. */
export function fmtAge(iso, now = Date.now()) {
  const minutes = Math.max(0, Math.round((now - new Date(iso).getTime()) / 60_000));
  if (minutes < 60) return "under an hour ago";
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}
