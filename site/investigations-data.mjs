import { validCoordinates, compactPlume } from "./consensus.mjs";
import { inRegion } from "./regions.mjs";
import { formatLocation } from "./overview.mjs";
import { analyzeThermalChange } from "./thermal-change.mjs";
const computedThermal = new WeakMap();

/** Review ordering only: points are neither probability nor operational severity. */
export function investigationPriority(event) {
  const thermal = computedThermal.get(event) ?? analyzeThermalChange(event);
  const contributions = [];
  if (numeric(thermal.priorityPoints) > 0) contributions.push({ label: "Thermal anomaly", points: thermal.priorityPoints, reason: thermal.label });
  if (event.category === "Requires Verification") contributions.push({ label: "Unexplained label", points: 25, reason: "Rule label requires verification; cause remains unexplained." });
  if (event.category === "Persistent Non-Industrial Thermal Source") contributions.push({ label: "Unexplained label", points: 15, reason: "Persistent heat without an industrial explanation in the rule label." });
  const model = event.model;
  if (model?.agrees === false && typeof model.label === "string" && model.label.trim() &&
      typeof event.category === "string" && model.label !== event.category && numeric(model.confidence) !== null && model.confidence <= 1) {
    contributions.push({ label: "Conflicting labels", points: 20, reason: `Rule/model label disagreement: ${event.category} / ${model.label}. Model agreement is not independent verification.` });
  }
  return { points: contributions.reduce((sum, c) => sum + c.points, 0), contributions, thermal,
    caveat: "Review priority points, not fire probability. Elevated thermal change adds 10; Requires Verification adds 25; unexplained persistent non-industrial heat adds 15; rule/model disagreement adds 20. Unexplained labels intentionally outweigh thermal change because change alone does not establish cause. Ties use risk score, then event ID. Stable heat does not establish safety." };
}

export const FEEDS = [
  { name: "national", url: "globe/data/events.json" },
  { name: "global", url: "globe/data/global-events.json" },
];
export const cellKey = (e) => `${Math.floor(e.longitude * 100)}:${Math.floor(e.latitude * 100)}`;
const dateValue = (s) => typeof s === "string" && Number.isFinite(Date.parse(s)) ? Date.parse(s) : -Infinity;
const observed = (e) => dateValue(e.evidence?.lastSeen) !== -Infinity ? dateValue(e.evidence.lastSeen) : dateValue(e.acqDate);
export const numeric = (v) => typeof v === "number" && Number.isFinite(v) && v >= 0 ? v : null;
const record = (v) => v && typeof v === "object" && !Array.isArray(v);
const string = (v) => typeof v === "string" ? v.slice(0, 4000) : null;
const strings = (v) => (Array.isArray(v) ? v : []).slice(0, 100).filter((s) => typeof s === "string").map(string);
function shaped(value, textKeys, numberKeys = []) {
  if (!record(value)) return null;
  return Object.fromEntries([...textKeys.map((k) => [k, string(value[k])]), ...numberKeys.map((k) => [k, numeric(value[k])])]);
}

/** Bound nested collections and never pass feed objects to the text-only DOM renderer. */
export function normalizeEvent(e) {
  const clean = shaped(e, ["id", "region", "state", "district", "country", "category", "riskLevel", "satellite", "daynight", "status", "acqDate", "riskSummary"],
    ["riskScore", "frp", "brightness", "confidence", "persistenceDays", "detectionCount", "priority"]);
  clean.latitude = e.latitude; clean.longitude = e.longitude;
  clean.place = typeof e.place === "string" ? string(e.place) : shaped(e.place, ["name", "country", "direction"], ["distanceKm"]);
  clean.facility = shaped(e.facility, ["name", "kind", "detail", "operator", "source", "ref"], ["distanceKm", "capacityMw"]);
  clean.evidence = shaped(e.evidence, ["firstSeen", "lastSeen"], ["detections", "days", "maxFrp", "meanFrp", "nightPasses", "lowConfidenceShare", "meanConfidence"]);
  if (clean.evidence && Array.isArray(e.evidence.satellites)) clean.evidence.satellites = strings(e.evidence.satellites);
  clean.satellites = strings(Array.isArray(e.satellites) ? e.satellites : [e.satellite]); clean.reasons = strings(e.reasons);
  if (clean.confidence > 100) clean.confidence = null;
  if (clean.evidence?.meanConfidence > 100) clean.evidence.meanConfidence = null;
  if (clean.evidence?.lowConfidenceShare > 1) clean.evidence.lowConfidenceShare = null;
  clean.riskFactors = (Array.isArray(e.riskFactors) ? e.riskFactors : []).slice(0, 100).filter((f) => record(f) && numeric(f.points) !== null && numeric(f.share) !== null && f.share <= 1)
    .map((f) => shaped(f, ["label", "value", "detail"], ["points", "share"]));
  clean.actions = (Array.isArray(e.actions) ? e.actions : []).slice(0, 100).filter(record).map((a) => shaped(a, ["step", "urgency", "detail"]));
  clean.model = shaped(e.model, ["label", "caveat"], ["confidence", "holdoutAgreement"]);
  if (clean.model && typeof e.model.agrees === "boolean") clean.model.agrees = e.model.agrees;
  else clean.model = null;
  clean.plume = shaped(e.plume, ["source", "observedAt"], ["windSpeedKmh", "coneLengthKm"]);
  if (clean.plume) {
    clean.plume.downwindBearingDeg = typeof e.plume.downwindBearingDeg === "number" && Number.isFinite(e.plume.downwindBearingDeg) ? e.plume.downwindBearingDeg : null;
    clean.plume.estimated = true;
  }
  clean.history = historyRows(e).slice(0, 2000);
  clean.historyTruncated = e.historyTruncated === true || Array.isArray(e.history) && e.history.length > 2000;
  // Analyze original samples before display filtering can hide invalid coverage.
  clean.thermalChange = analyzeThermalChange({ ...e, historyTruncated: clean.historyTruncated });
  computedThermal.set(clean, clean.thermalChange);
  clean.corroborated = typeof e.corroborated === "boolean" ? e.corroborated : null;
  return clean;
}

export function snapshotFreshness(iso, now = Date.now()) {
  const stamp = dateValue(iso);
  if (stamp === -Infinity) return { warning: true, label: "Snapshot freshness unavailable: invalid or missing timestamp." };
  if (stamp > now + 5 * 60 * 1000) return { warning: true, label: "Snapshot freshness unavailable: timestamp is in the future." };
  const hours = Math.max(0, (now - stamp) / 3600000);
  return { warning: hours > 12, label: hours > 12 ? `Stale snapshot: ${Math.floor(hours)} hours old (>12h).` : `Snapshot age: ${Math.floor(hours)} hours.` };
}

export function validateFeed(data) {
  if (!data || !Array.isArray(data.events) || data.events.length > 100000 ||
      !data.meta || !["firms_live", "local_cache", "mixed"].includes(data.meta.source)) {
    throw new Error("Unavailable or unsupported live-feed schema");
  }
  const events = data.events.filter((e) => e && typeof e.id === "string" && e.id.length > 0 &&
    e.id.length <= 160 && validCoordinates(e.latitude, e.longitude));
  return { events: events.map(normalizeEvent), meta: data.meta, rejected: data.events.length - events.length };
}

/** Keep whole records: borrowing old national evidence would misstate the new observation. */
export function mergeFeeds(feeds) {
  const cells = new Map();
  for (const feed of feeds) {
    for (const e of feed.events) {
      const candidate = { ...e, provenance: {
        feed: feed.name, url: feed.url, source: feed.meta.source,
        scope: feed.meta.scope ?? feed.name, generatedAt: feed.meta.generatedAt ?? null,
        windowDays: feed.meta.windowDays ?? null, partial: feed.meta.partial === true,
        historyScope: string(feed.meta.historyScope),
        attribution: Array.isArray(feed.meta.attribution) ? feed.meta.attribution.filter((v) => typeof v === "string") : [],
      }, aliases: [e.id] };
      if (computedThermal.has(e)) computedThermal.set(candidate, computedThermal.get(e));
      const key = cellKey(e), previous = cells.get(key);
      if (!previous) { cells.set(key, candidate); continue; }
      const aliases = [...new Set([...previous.aliases, e.id])];
      const newer = observed(candidate) > observed(previous) ||
        (observed(candidate) === observed(previous) &&
          (candidate.provenance.feed === "national" && previous.provenance.feed !== "national" ||
           candidate.provenance.feed === previous.provenance.feed &&
           dateValue(candidate.provenance.generatedAt) > dateValue(previous.provenance.generatedAt)));
      const winner = newer ? candidate : previous;
      winner.aliases = aliases;
      cells.set(key, winner);
    }
  }
  return [...cells.values()];
}

export async function fetchInvestigations(fetcher = globalThis.fetch) {
  const settled = await Promise.allSettled(FEEDS.map(async (feed) => {
    const response = await fetcher(feed.url, { cache: "no-cache", signal: AbortSignal.timeout(20000) });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return { ...feed, ...validateFeed(await response.json()) };
  }));
  const feeds = [], failures = [];
  settled.forEach((result, i) => {
    if (result.status === "fulfilled") feeds.push(result.value);
    else failures.push({ ...FEEDS[i], error: String(result.reason?.message ?? result.reason) });
  });
  return { events: mergeFeeds(feeds), feeds, failures };
}

export function queryCases(events, filters = {}, reviews = new Map()) {
  const q = (filters.search ?? "").trim().toLowerCase();
  const filtered = events.filter((e) => inRegion(e, filters.region ?? "india") &&
    (!q || [e.id, ...e.aliases ?? [], formatLocation(e), e.category, e.facility?.name].some((v) => String(v ?? "").toLowerCase().includes(q))) &&
    (!filters.severity || e.riskLevel === filters.severity) &&
    (!filters.category || e.category === filters.category) &&
    (!filters.persistence || numeric(e.persistenceDays) !== null && e.persistenceDays >= Number(filters.persistence)) &&
    (!filters.plumes || validCoordinates(e.latitude, e.longitude) && !!compactPlume(e.plume)) &&
    (!filters.bookmarks || reviews.get(cellKey(e))?.bookmark === true) &&
    (!filters.status || (reviews.get(cellKey(e))?.status ?? "unreviewed") === filters.status));
  const sort = filters.sort ?? "priority";
  const key = { risk: "riskScore", persistence: "persistenceDays", frp: "frp" }[sort];
  const ascending = filters.direction === "asc";
  const priorities = sort === "priority" ? new Map(filtered.map((e) => [e, investigationPriority(e).points])) : null;
  return filtered.sort((a, b) => {
    if (priorities) return (ascending ? 1 : -1) * (priorities.get(a) - priorities.get(b)) ||
      (numeric(b.riskScore) ?? -Infinity) - (numeric(a.riskScore) ?? -Infinity) || a.id.localeCompare(b.id);
    const av = key ? numeric(a[key]) : observed(a), bv = key ? numeric(b[key]) : observed(b);
    if (av === null && bv !== null) return 1;
    if (bv === null && av !== null) return -1;
    return (ascending ? 1 : -1) * ((av ?? -Infinity) - (bv ?? -Infinity)) || a.id.localeCompare(b.id);
  });
}

export function paginateCases(events, page = 1) {
  const pages = Math.max(1, Math.ceil(events.length / 50));
  const current = Math.min(pages, Math.max(1, Math.trunc(page) || 1));
  return { events: events.slice((current - 1) * 50, current * 50), page: current, pages, total: events.length };
}

export function historyRows(event) {
  return (Array.isArray(event.history) ? event.history : []).filter((row) => row &&
    typeof row.date === "string" && Number.isFinite(Date.parse(row.date)) && numeric(row.frp) !== null)
    .map((row) => ({ date: row.date, frp: row.frp, confidence:
      numeric(row.confidence) !== null && row.confidence <= 100 ? row.confidence : null,
      ...Object.fromEntries(["satellite", "instrument", "daynight"].filter((key) => Object.hasOwn(row, key)).map((key) => [key, string(row[key])])),
      ...(Object.hasOwn(row, "synthetic") ? { synthetic: row.synthetic !== false } : {}),
      ...(Object.hasOwn(row, "frpObserved") ? { frpObserved: row.frpObserved === true ? true : row.frpObserved == null ? null : false } : {}),
    }))
    .sort((a, b) => a.date.localeCompare(b.date));
}

export function globeLink(event, region) {
  if (!validCoordinates(event.latitude, event.longitude)) return null;
  return `globe/?${new URLSearchParams({ region, event: event.id, lat: String(event.latitude), lon: String(event.longitude), z: "8" })}`;
}
