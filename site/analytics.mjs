/*
 * Aggregations for the public Analytics page — the same breakdowns as the
 * dashboard's Analytics page (app.py _render_analytics /
 * _render_national_analytics), computed client-side from the same
 * events.json. Every bar's color is decided here (never guessed in the
 * renderer): the fixed risk/category tokens keep their meaning, and a single
 * ranked measure (states, satellites, FRP, persistence) uses one series hue,
 * never the reserved accent.
 */
import { CATEGORY_COLORS, MUTED, RISK_COLORS, SERIES } from "./overview.mjs";

function countBy(events, keyFn) {
  const counts = new Map();
  for (const e of events) {
    const key = keyFn(e);
    if (key == null || key === "") continue;
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return counts;
}

/** Ranked by count, most active first — matching the dashboard's own
 * `value_counts()` bar. Color still comes from the fixed category→hue map,
 * never from rank. */
export function categoryCounts(events) {
  const counts = countBy(events, (e) => e.category);
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([key, count]) => ({ key, label: key, count, color: CATEGORY_COLORS[key] ?? MUTED }));
}

const RISK_ORDER = ["LOW", "MODERATE", "HIGH", "CRITICAL"];

/** Fixed low→critical order, not sorted by count — the order itself is part
 * of what the chart says. */
export function riskCounts(events) {
  const counts = countBy(events, (e) => e.riskLevel);
  return RISK_ORDER.map((key) => ({
    key,
    label: key.charAt(0) + key.slice(1).toLowerCase(),
    count: counts.get(key) ?? 0,
    color: RISK_COLORS[key],
  }));
}

/** Every state with activity, most hotspots first. One series hue: the bars
 * rank one measure across places, they are not separate named series. */
export function topStates(events, n = 10) {
  const counts = countBy(events, (e) => e.state);
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, n)
    .map(([state, count]) => ({ key: state, label: state, count, color: SERIES }));
}

const SATELLITE_LABELS = {
  "VIIRS S-NPP": "Suomi NPP VIIRS",
  "VIIRS NOAA-20": "NOAA-20 VIIRS",
  "VIIRS NOAA-21": "NOAA-21 VIIRS",
  "MODIS Aqua": "Aqua MODIS",
  "MODIS Terra": "Terra MODIS",
};

export function satelliteCounts(events) {
  const counts = countBy(events, (e) => e.satellite);
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .map(([key, count]) => ({ key, label: SATELLITE_LABELS[key] ?? key, count, color: SERIES }));
}

/** A round bin width covering `max` in at most ~`targetBins` steps: 1/2/5 ×
 * a power of ten, the same "clean numbers" rule the mark spec asks axis
 * ticks to follow. */
function niceStep(max, targetBins) {
  if (max <= 0) return 1;
  const raw = max / targetBins;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  for (const step of [1, 2, 5, 10]) {
    if (raw <= step * magnitude) return step * magnitude;
  }
  return 10 * magnitude;
}

/** FRP (MW) bucketed into clean-width bins, most intense last — matching the
 * dashboard's own histogram, coarsened to rows a person reads as text. */
export function frpHistogram(events, targetBins = 10) {
  const values = events.map((e) => e.frp).filter((v) => typeof v === "number" && v >= 0);
  if (!values.length) return [];
  const max = Math.max(...values);
  const step = niceStep(max, targetBins);
  const binCount = Math.max(1, Math.ceil(max / step));
  const bins = Array.from({ length: binCount }, () => 0);
  for (const v of values) bins[Math.min(binCount - 1, Math.floor(v / step))] += 1;
  return bins.map((count, i) => ({
    key: String(i),
    label: i === binCount - 1 ? `${(i * step).toFixed(0)}+ MW` : `${(i * step).toFixed(0)}–${((i + 1) * step).toFixed(0)} MW`,
    count,
    color: SERIES,
  }));
}

const PERSISTENCE_BUCKETS = [
  ["0", 0, 0],
  ["1", 1, 1],
  ["2–3", 2, 3],
  ["4–6", 4, 6],
  ["7–13", 7, 13],
  ["14–29", 14, 29],
  ["30+", 30, Infinity],
];

/** Days active, bucketed the same way the rest of the product talks about
 * persistence (config.NATIONAL_PERSISTENCE_MIN_DAYS_HISTORY = 5 falls inside
 * the 4–6 bucket; PERSISTENT status starts at 14). */
export function persistenceCounts(events) {
  return PERSISTENCE_BUCKETS.map(([label, lo, hi]) => ({
    key: label,
    label: `${label} day${label === "1" ? "" : "s"}`,
    count: events.filter((e) => (e.persistenceDays ?? 0) >= lo && (e.persistenceDays ?? 0) <= hi).length,
    color: SERIES,
  }));
}
