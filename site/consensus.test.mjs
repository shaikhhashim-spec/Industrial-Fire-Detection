import assert from "node:assert/strict";
import { test } from "node:test";
import { evaluateConsensus, compactPlume, compass16, validCoordinates } from "./consensus.mjs";

const event = { latitude: 20, longitude: 73, frp: 100, confidence: 80,
  persistenceDays: 5, detectionCount: 10, evidence: { nightPasses: 1, lowConfidenceShare: 0, satellites: ["A", "B"] } };
const plume = { windSpeedKmh: 20, coneLengthKm: 12, downwindBearingDeg: 450 };

test("screening is deterministic, signed, bounded and separate from risk", () => {
  const input = structuredClone({ ...event, riskScore: 99, riskLevel: "CRITICAL" });
  const before = structuredClone(input);
  const result = evaluateConsensus(input);
  assert.deepEqual(result, evaluateConsensus(input));
  assert.deepEqual(input, before);
  assert.equal(result.mode, "rule-based");
  assert.equal(result.index, 95);
  assert.equal(result.verdict, "Verification required");
  assert.equal(result.sentinel.points + result.skeptic.points + result.arbiter.points, result.index);
  assert.ok(result.sentinel.evidence.every((s) => /^\+\d+ pts:/.test(s)));
  assert.match(result.limitations.join(" "), /not probability or a confirmed fire/);
});

test("wind and model confidence cannot raise evidence strength or confirm fire", () => {
  const base = evaluateConsensus(event);
  const windy = evaluateConsensus({ ...event, plume, model: { confidence: 1, agrees: true } });
  assert.equal(windy.index, base.index);
  assert.match(windy.arbiter.evidence.join(" "), /wind.*not confirmation/i);
  assert.match(windy.skeptic.evidence.join(" "), /cannot validate correctness/);
});

test("missing context is explicitly unavailable, never synthesized from labels or coordinates", () => {
  const result = evaluateConsensus({ category: "Sun Glint / False Positive", latitude: 0, longitude: 0, daynight: "N" });
  assert.equal(result.index, 0);
  for (const label of ["Glint angles", "Cloud cover", "Agricultural burn calendar", "Water context", "Population context", "Night-pass"])
    assert.match(result.skeptic.evidence.join(" "), new RegExp(`${label}.*unavailable`, "i"));
});

test("nullable, nonfinite, out of range and numeric strings are unavailable", () => {
  for (const value of [null, undefined, NaN, Infinity, -1, 101, "80"])
    assert.equal(evaluateConsensus({ confidence: value }).index, 0);
  assert.equal(evaluateConsensus({ confidence: 80 }).index, evaluateConsensus({ evidence: { meanConfidence: 80 } }).index);
  assert.equal(evaluateConsensus({ confidence: 80, evidence: { meanConfidence: null } }).index, 0);
  assert.equal(evaluateConsensus({ confidence: 0.8 }).index, 0); // never multiply normalized-looking confidence
  assert.equal(evaluateConsensus(null).index, 0);
});

test("quality challenges lower evidence and facilities require actual close proximity", () => {
  const base = evaluateConsensus(event).index;
  assert.ok(evaluateConsensus({ ...event, corroborated: false }).index < base);
  assert.ok(evaluateConsensus({ ...event, confidence: 20 }).index < base);
  assert.ok(evaluateConsensus({ ...event, evidence: { ...event.evidence, lowConfidenceShare: 1 } }).index < base);
  for (const distanceKm of [null, undefined, NaN, Infinity, -1, 100])
    assert.equal(evaluateConsensus({ ...event, facility: { name: "Plant", distanceKm } }).index, base);
  assert.equal(evaluateConsensus({ ...event, facility: { name: "Plant", distanceKm: 2 } }).index, base - 10);
});

test("compact plume normalizes 16 compass points and omits invalid values", () => {
  assert.equal(compass16(450), "E");
  assert.equal(compass16(-22.5), "NNW");
  for (let i = 0; i < 16; i++) assert.equal(new Set(Array.from({ length: 16 }, (_, j) => compass16(j * 22.5))).size, 16);
  assert.equal(compactPlume(plume).downwindBearingDeg, 90);
  assert.equal(compactPlume(plume).label, "Estimated plume E 12.0 km");
  for (const key of ["windSpeedKmh", "coneLengthKm", "downwindBearingDeg"])
    for (const v of [null, undefined, NaN, Infinity, "10"])
      assert.equal(compactPlume({ ...plume, [key]: v }), null);
  assert.equal(compactPlume({ ...plume, windSpeedKmh: 0 }), null);
  assert.equal(compactPlume({ ...plume, coneLengthKm: -1 }), null);
  assert.equal(validCoordinates(null, 0), false);
  assert.equal(validCoordinates(91, 180), false);
});
