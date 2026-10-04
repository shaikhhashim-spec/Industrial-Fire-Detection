/** Daily screening contract, mirrored by the offline exporter and parity tests.
 * Baseline: median of daily peaks in the preceding 30 days, with at least
 * three days covering every current satellite/instrument/day-night group.
 * observationDays excludes current; gaps counts unmatched days from the first
 * available prior observation to current. Missing measurements are never zero.
 */
const DAY = 86400000;
const CAVEAT = "Thermal change is a screening signal, not confirmation of fire or its cause.";
const COVERAGE = "Cloud, overpass and pixel coverage can change daily peaks; gaps are not zero heat.";
const ALIASES = new Map([
  ["N", "VIIRS S-NPP"], ["S-NPP", "VIIRS S-NPP"], ["VIIRS_SNPP_NRT", "VIIRS S-NPP"],
  ["N20", "VIIRS NOAA-20"], ["NOAA-20", "VIIRS NOAA-20"], ["VIIRS_NOAA20_NRT", "VIIRS NOAA-20"],
  ["N21", "VIIRS NOAA-21"], ["NOAA-21", "VIIRS NOAA-21"], ["VIIRS_NOAA21_NRT", "VIIRS NOAA-21"],
  ["AQUA", "MODIS Aqua"], ["AQUA (MODIS)", "MODIS Aqua"],
  ["TERRA", "MODIS Terra"], ["TERRA (MODIS)", "MODIS Terra"],
  ...["VIIRS S-NPP", "VIIRS NOAA-20", "VIIRS NOAA-21", "MODIS Aqua", "MODIS Terra"].map(s => [s.toUpperCase(), s]),
]);
function day(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value) || value.startsWith("0000")) return null;
  const stamp = Date.parse(value);
  return Number.isFinite(stamp) && new Date(stamp).toISOString().slice(0, 10) === value ? stamp / DAY : null;
}
function group(row) {
  const satellite = ALIASES.get(String(row.satellite ?? "").trim().toUpperCase());
  if (!satellite || !["D", "N"].includes(row.daynight)) return null;
  const instrument = satellite.startsWith("VIIRS") ? "VIIRS" : "MODIS";
  if (row.instrument && String(row.instrument).trim().toUpperCase() !== instrument) return null;
  return `${satellite}|${instrument}|${row.daynight}`;
}
const median = values => {
  const sorted = [...values].sort((a, b) => a - b), mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : sorted[mid - 1] / 2 + sorted[mid] / 2;
};
const round = value => Math.abs(value) >= 1e15 ? value : Math.round((value + Number.EPSILON) * 10) / 10;

export function analyzeThermalChange(event) {
  const result = { status: "insufficient_history", label: "Insufficient history", baselineFrp: null,
    currentFrp: null, changePercent: null, observationDays: 0, gaps: 0,
    limitations: [CAVEAT, COVERAGE], reasons: [], priorityPoints: 0 };
  const fail = reason => { result.reasons.push(reason); return result; };
  const currentDay = day(event?.acqDate);
  if (currentDay === null) return fail("A valid current acquisition date is required.");
  if (event?.historyTruncated) return fail("History was truncated; complete daily coverage is unavailable.");
  const daily = new Map(), unusableDays = new Set();
  let invalid = false, unknown = false, unobserved = false, currentInvalid = false, first = currentDay;
  for (const row of Array.isArray(event?.history) ? event.history : []) {
    const date = day(row?.date);
    if (date === null) { invalid = true; continue; }
    if (date > currentDay || date < currentDay - 30) continue;
    first = Math.min(first, date);
    const key = row && group(row);
    const observed = (row?.frpObserved == null || row.frpObserved === true) && (row?.frp !== 0 || row.frpObserved === true);
    const usable = typeof row?.frp === "number" && Number.isFinite(row.frp) && row.frp >= 0 && !row.synthetic && observed;
    if (!usable || !key) {
      unusableDays.add(date);
      invalid ||= !usable; unknown ||= !key; unobserved ||= !observed;
      currentInvalid ||= date === currentDay;
      continue;
    }
    if (!daily.has(date)) daily.set(date, new Map());
    const groups = daily.get(date);
    groups.set(key, Math.max(groups.get(key) ?? -Infinity, row.frp));
  }
  if (invalid) result.limitations.push("Invalid or synthetic history measurements were excluded.");
  if (unknown) result.limitations.push("History lacks reliable satellite/instrument/day-night metadata.");
  if (unobserved) result.limitations.push("Unobserved FRP and legacy zeros without measurement provenance are excluded.");
  result.gaps = currentDay - first;
  const current = daily.get(currentDay);
  if (!current || currentInvalid) return fail("Current-day observations with reliable sensor/pass metadata are required; the event window peak is not current FRP.");
  result.currentFrp = round(Math.max(...current.values()));
  const peaks = [];
  for (const [date, groups] of daily) {
    if (date < currentDay && !unusableDays.has(date) && [...current.keys()].every(key => groups.has(key))) {
      peaks.push(Math.max(...[...current.keys()].map(key => groups.get(key))));
    }
  }
  result.observationDays = peaks.length;
  result.gaps = currentDay - first - peaks.length;
  if (result.gaps) result.limitations.push("Some calendar days lack comparable observations.");
  if (peaks.length < 3) return fail("At least three prior observation days with matching sensor/pass coverage are required.");
  const baseline = median(peaks), currentPeak = Math.max(...current.values());
  result.baselineFrp = round(baseline);
  if (baseline <= 0) return fail("A positive baseline is required for a percentage comparison.");
  const percent = (currentPeak - baseline) / baseline * 100, delta = currentPeak - baseline;
  if (!Number.isFinite(percent)) return fail("FRP range prevents a finite percentage comparison.");
  result.changePercent = round(percent);
  result.status = percent >= 50 && delta >= 5 ? "elevated" : percent <= -100 / 3 && delta <= -5 ? "reduced" : "stable";
  result.label = { elevated: "Elevated thermal output", reduced: "Reduced thermal output", stable: "Recurring thermal activity; no substantial change" }[result.status];
  result.priorityPoints = result.status === "elevated" ? 10 : 0;
  result.reasons.push("Current daily peak compared with the median of prior daily peaks using matching sensor/pass coverage.");
  return result;
}
