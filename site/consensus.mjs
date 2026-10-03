/** Deterministic evidence screening; no inference of fire cause or dispatch. */
const finite = (v, min = 0, max = Infinity) =>
  typeof v === "number" && Number.isFinite(v) && v >= min && v <= max ? v : null;
const COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];

export function validCoordinates(latitude, longitude) {
  return finite(latitude, -90, 90) !== null && finite(longitude, -180, 180) !== null;
}

export function compass16(bearing) {
  if (typeof bearing !== "number" || !Number.isFinite(bearing)) return null;
  return COMPASS[Math.round(((bearing % 360 + 360) % 360) / 22.5) % 16];
}

/** Compact wind context. Invalid, calm, or zero-length estimates are omitted. */
export function compactPlume(plume) {
  if (!plume || typeof plume !== "object") return null;
  const speed = finite(plume.windSpeedKmh);
  const length = finite(plume.coneLengthKm);
  const direction = compass16(plume.downwindBearingDeg);
  if (!(speed > 0) || !(length > 0) || !direction) return null;
  const bearing = (plume.downwindBearingDeg % 360 + 360) % 360;
  const source = typeof plume.source === "string" ? plume.source.toLowerCase() : "";
  const provenance = /fallback|default|unverified|unknown/.test(source) ? " (fallback/unverified wind)"
    : /cache|stale/.test(source) ? " (cached/unverified wind)" : plume.estimated === true ? " (unverified wind)" : "";
  return {
    windSpeedKmh: speed, coneLengthKm: length, downwindBearingDeg: bearing, direction,
    label: `Estimated plume ${direction} ${length.toFixed(1)} km${provenance}`,
    estimated: true,
  };
}

export function evaluateConsensus(event = {}) {
  const e = event && typeof event === "object" ? event : {};
  const data = e.evidence && typeof e.evidence === "object" ? e.evidence : {};
  // Explicit invalid/null evidence stays unavailable rather than borrowing a default.
  const read = (key, fallback, max = Infinity) => finite(Object.hasOwn(data, key) ? data[key] : e[fallback], 0, max);
  const frp = read("maxFrp", "frp");
  const confidence = read("meanConfidence", "confidence", 100);
  const days = read("days", "persistenceDays");
  const detections = read("detections", "detectionCount");
  const night = read("nightPasses", "nightPasses");
  const lowShare = read("lowConfidenceShare", "lowConfidenceShare", 1);
  const satellites = [...new Set((Array.isArray(data.satellites) ? data.satellites : Array.isArray(e.satellites) ? e.satellites : [e.satellite])
    .filter((s) => typeof s === "string" && s.trim()))];
  const support = [], challenges = [], unknowns = [];
  const add = (list, key, points, reason) => list.push({ key, points, reason });
  if (frp !== null) add(support, "frp", Math.round(Math.min(frp / 100, 1) * 35), `Peak radiative power: ${frp} MW; a thermal signal, not its cause.`);
  else unknowns.push("Peak radiative power unavailable.");
  if (confidence !== null) {
    add(support, "confidence", Math.round(confidence * 0.25), `Satellite confidence: ${confidence}/100; not fire probability.`);
    if (confidence < 50) add(challenges, "low-confidence", -10, "Low satellite confidence weakens the thermal evidence.");
  } else unknowns.push("Satellite confidence unavailable (requires a finite value from 0 to 100).");
  if (days !== null) {
    add(support, "persistence", Math.round(Math.min(days / 5, 1) * 15), `Observed on ${days} day(s); persistence does not establish fire cause.`);
    if (days > 1) add(challenges, "persistent-source", 0, "Recurring heat may reflect a stable industrial or other non-fire source.");
  } else unknowns.push("Persistence unavailable.");
  if (detections !== null) add(support, "detections", detections >= 2 ? 10 : 0, `${detections} detections; repeated pixels may not be independent.`);
  else unknowns.push("Detection count unavailable.");
  if (night !== null) add(support, "night", night > 0 ? 5 : 0, `${night} night pass(es); night observations reduce some daytime ambiguity.`);
  else unknowns.push("Night-pass evidence unavailable; glint cannot be ruled out.");
  if (satellites.length) add(support, "satellites", satellites.length > 1 ? 10 : 0, `${satellites.length} satellite source(s); cross-source timing and independence require review.`);
  else unknowns.push("Satellite sources unavailable.");
  if (lowShare !== null && lowShare > 0) add(challenges, "low-confidence-share", -Math.round(lowShare * 15), `${Math.round(lowShare * 100)}% of detections have low confidence.`);
  if (lowShare === null) unknowns.push("Low-confidence detection share unavailable.");
  if (e.corroborated === false) add(challenges, "uncorroborated", -10, "The event explicitly reports no corroboration.");
  const facilityDistance = finite(e.facility?.distanceKm);
  if (e.facility && typeof e.facility.name === "string" && e.facility.name.trim()) {
    if (facilityDistance !== null && facilityDistance <= 2) add(challenges, "facility", -10, `Mapped facility within ${facilityDistance} km (${e.facility.name}) offers an alternative heat source; proximity does not establish cause.`);
    else if (facilityDistance === null) unknowns.push("Facility proximity unavailable; a name alone cannot identify the heat source.");
  }
  if (e.model) add(challenges, "model", 0, "Model confidence or agreement cannot validate correctness; reproducing rule labels is not independent verification.");
  for (const label of ["Glint angles", "Cloud cover", "Agricultural burn calendar", "Water context", "Population context"]) {
    // These exports have no verified schema for these layers. Never synthesize them.
    unknowns.push(`${label} unavailable to this screening engine.`);
  }
  const plume = validCoordinates(e.latitude, e.longitude) ? compactPlume(e.plume) : null;
  const wind = plume ? `${plume.label}; wind ${plume.windSpeedKmh.toFixed(1)} km/h. Wind is dispersion context, not confirmation.` : "Valid wind/plume context unavailable.";
  const limitations = [
    "Deterministic rule-based screening; no LLMs or autonomous agents are involved.",
    "Index is heuristic evidence strength from 0 to 100, not probability or a confirmed fire.",
    "Satellite detections, persistence and radiative power cannot establish cause or ground impact.",
    "Existing risk and recommendations are separate; screening does not change risk or automatically dispatch responders.",
    "Model confidence cannot validate correctness.",
    "Wind/plume estimates are visual context, not observed smoke or scientific dispersion forecasts.",
  ];
  const index = Math.max(0, Math.min(100, support.concat(challenges).reduce((sum, c) => sum + c.points, 0)));
  const role = (summary, items, extra = []) => ({ summary,
    points: items.reduce((sum, c) => sum + c.points, 0),
    evidence: items.map((c) => `${c.points >= 0 ? "+" : ""}${c.points} pts: ${c.reason}`).concat(extra),
  });
  return {
    mode: "rule-based", index, verdict: "Verification required", limitations,
    sentinel: role(`${support.length} available thermal evidence components; ${index}/100 after challenges.`, support),
    skeptic: role("Alternative heat sources, observation quality and missing context require review.", challenges, unknowns),
    arbiter: role(`Verification required. Evidence index ${index}/100.`, [], [wind, "Human verification required; no automatic dispatch."]),
  };
}
