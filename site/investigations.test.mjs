import { test } from "node:test";
import assert from "node:assert/strict";
import { mergeFeeds, fetchInvestigations, queryCases, paginateCases, historyRows, globeLink, cellKey, validateFeed, snapshotFreshness } from "./investigations-data.mjs";
import { parseReviews, serializeReviews, mergeReviews, readReviews, writeReviews, MAX_IMPORT_BYTES } from "./investigations-reviews.mjs";
import { reportSnapshot, reportCsv, csvCell } from "./investigations-reports.mjs";
import { compactPlume } from "./consensus.mjs";

const event = (over = {}) => ({ id: "TH-1", latitude: 20.123, longitude: 85.123, acqDate: "2026-10-01", riskScore: 80, riskLevel: "HIGH", frp: 45, persistenceDays: 5, category: "Requires Verification", ...over });
const feed = (name, events, over = {}) => ({ name, url: `${name}.json`, events, meta: { source: "firms_live", generatedAt: "2026-10-02T00:00:00Z", attribution: ["NASA FIRMS"], ...over } });
const review = (over = {}) => ({ cell: "8512:2012", eventId: "TH-1", status: "in-review", notes: "personal annotation", bookmark: true, updatedAt: "2026-10-03T00:00:00.000Z", ...over });
const file = (rows) => JSON.stringify({ version: 1, reviews: rows });

test("nested malformed evidence is normalized to bounded text-only shapes", () => {
  const raw = event({ facility: { name: { hostile: true }, distanceKm: -4 }, evidence: [], place: [],
    satellite: "VIIRS", riskSummary: {}, model: { label: {}, agrees: [] },
    riskFactors: [null, {}, { label: {}, points: 2, share: .2, value: {} }],
    actions: [null, { step: {}, detail: ["bad"], urgency: {} }], reasons: [null, {}, "safe"],
    history: Array.from({ length: 2500 }, () => ({ date: "2026-10-01", frp: 2, confidence: {} })) });
  const clean = validateFeed({ events: [raw], meta: { source: "firms_live" } }).events[0];
  assert.equal(clean.facility.name, null); assert.equal(clean.facility.distanceKm, null);
  assert.equal(clean.evidence, null); assert.equal(clean.model, null);
  assert.equal(clean.riskFactors[0].label, null); assert.equal(clean.actions[0].step, null);
  assert.deepEqual(clean.reasons, ["safe"]); assert.deepEqual(clean.satellites, ["VIIRS"]);
  assert.equal(clean.history.length, 2000); assert.equal(clean.historyTruncated, true);
  assert.equal(clean.history[0].confidence, null);
});

test("freshness warns on stale, future, invalid and missing timestamps", () => {
  const now = Date.parse("2026-10-03T12:00:00Z");
  assert.equal(snapshotFreshness("2026-10-03T06:00:00Z", now).warning, false);
  assert.match(snapshotFreshness("2026-10-02T12:00:00Z", now).label, /Stale/);
  assert.match(snapshotFreshness("2026-10-04T12:00:00Z", now).label, /future/);
  assert.equal(snapshotFreshness("bad", now).warning, true);
  assert.equal(snapshotFreshness(null, now).warning, true);
});

test("normalization preserves actual exporter wind source, cached and fallback labels", () => {
  for (const source of ["cache", "stale_cache", "offline_fallback", "unknown", "open-meteo"]) {
    const raw = event({ plume: { source, observedAt: "2026-10-03T10:00", estimated: true, windSpeedKmh: 12, coneLengthKm: 3, downwindBearingDeg: 45 } });
    const clean = validateFeed({ events: [raw], meta: { source: "firms_live" } }).events[0];
    assert.equal(clean.plume.source, source); assert.equal(clean.plume.observedAt, raw.plume.observedAt);
    const label = compactPlume(clean.plume).label;
    if (/cache/.test(source)) assert.match(label, /cached\/unverified/);
    else if (/fallback|unknown/.test(source)) assert.match(label, /fallback\/unverified/);
    else assert.match(label, /unverified wind/);
  }
});

test("merge uses whole newer observation, national ties, cell boundaries and aliases", () => {
  const n = event({ evidence: { lastSeen: "2026-10-03" }, history: [{ date: "2026-10-03", frp: 3 }] });
  const g = event({ id: "G-1", acqDate: "2026-10-02", history: [] });
  let result = mergeFeeds([feed("global", [g]), feed("national", [n])]);
  assert.equal(result.length, 1); assert.equal(result[0].id, "TH-1");
  assert.deepEqual(new Set(result[0].aliases), new Set(["TH-1", "G-1"]));
  result = mergeFeeds([feed("national", [n]), feed("global", [event({ id: "G-2", acqDate: "2026-10-04", history: [] })])]);
  assert.equal(result[0].id, "G-2"); assert.deepEqual(result[0].history, []);
  assert.equal(result[0].provenance.feed, "global");
  assert.equal(mergeFeeds([feed("national", [event()]), feed("global", [event({ id: "G", latitude: 20.129 })])])[0].id, "TH-1");
  assert.equal(mergeFeeds([feed("national", [event(), event({ id: "other", latitude: 20.131 })])]).length, 2);
  assert.equal(cellKey(event({ longitude: -0.001, latitude: -0.001 })), "-1:-1");
});

test("both independent feed failure directions preserve working records and provenance", async () => {
  for (const failed of ["global", "national"]) {
    const result = await fetchInvestigations(async (url) => {
      const name = url.includes("global-") ? "global" : "national";
      if (name === failed) throw new Error("network unavailable");
      return { ok: true, json: async () => ({ events: [event()], meta: { source: "firms_live", scope: name, partial: true } }) };
    });
    assert.equal(result.events.length, 1); assert.equal(result.failures[0].name, failed);
    assert.equal(result.events[0].provenance.partial, true);
  }
  const result = await fetchInvestigations(async () => ({ ok: false, status: 503 }));
  assert.equal(result.failures.length, 2); assert.deepEqual(result.events, []);
});

test("feed rejects mock data and invalid coordinates without inventing evidence", () => {
  assert.throws(() => validateFeed({ events: [], meta: { source: "mock" } }));
  const result = validateFeed({ meta: { source: "local_cache" }, events: [event(), event({ latitude: null }), event({ longitude: 181 })] });
  assert.equal(result.events.length, 1); assert.equal(result.rejected, 2);
  assert.deepEqual(historyRows(event()), []);
  assert.deepEqual(historyRows(event({ history: [{ date: "2026-01-01", frp: null }, { date: "bad", frp: 4 }, { date: "2026-01-03", frp: 0, confidence: 200 }] })), [{ date: "2026-01-03", frp: 0, confidence: null }]);
});

test("regional search, combined filters, unknown-last sorting and 50-record pagination", () => {
  const events = mergeFeeds([feed("national", [event({ facility: { name: "Steel <works>" }, plume: { windSpeedKmh: 4, coneLengthKm: 1, downwindBearingDeg: 0 } }), event({ id: "unknown", riskScore: null }), event({ id: "outside", latitude: -20, longitude: 120 })])]);
  // These fixtures occupy distinct cells so they are separate queue cases.
  const a = { ...events[0], id: "A", longitude: 85.2 }, b = { ...a, id: "B", longitude: 85.3, riskScore: null };
  const rows = [a, b, event({ id: "outside", latitude: -20, longitude: 120 })];
  assert.equal(queryCases(rows, { region: "india", sort: "risk", direction: "asc" }).at(-1).id, "B");
  const reviews = new Map([[cellKey(a), review()]]);
  assert.equal(queryCases(rows, { region: "india", search: "Steel <works>", severity: "HIGH", persistence: "5", plumes: true, bookmarks: true, status: "in-review" }, reviews).length, 1);
  assert.equal(queryCases(rows, { region: "australia" }).length, 1);
  const many = Array.from({ length: 121 }, (_, i) => event({ id: `X${i}` }));
  assert.equal(paginateCases(many, 2).events.length, 50);
  assert.equal(paginateCases(many, 9).events.length, 21);
  assert.equal(paginateCases([], -1).page, 1);
});

test("globe link selects winning ID and valid coordinates", () => {
  const link = globeLink(event({ id: "TH +&" }), "india");
  const url = new URL(link, "https://example.com/project/");
  assert.equal(url.pathname, "/project/globe/");
  assert.equal(url.searchParams.get("event"), "TH +&"); assert.equal(url.searchParams.get("lat"), "20.123");
  assert.equal(url.searchParams.get("z"), "8");
  assert.equal(globeLink(event({ latitude: NaN }), "india"), null);
});

test("review round-trip, timestamps and newer-only merge preserve local edits", () => {
  const rows = parseReviews(file([review()])), original = new Map(rows.map((r) => [r.cell, r]));
  assert.deepEqual(parseReviews(serializeReviews(original)), rows);
  assert.equal(mergeReviews(original, [review({ notes: "older", updatedAt: "2026-10-02T00:00:00Z" })]).get("8512:2012").notes, "personal annotation");
  assert.equal(mergeReviews(original, [review({ notes: "equal" })]).get("8512:2012").notes, "personal annotation");
  assert.equal(mergeReviews(original, [review({ notes: "newer", updatedAt: "2026-10-04T00:00:00Z" })]).get("8512:2012").notes, "newer");
});

test("review import rejects unbounded, unknown, prototype, duplicate and invalid fields atomically", () => {
  for (const r of [review({ notes: "x".repeat(10001) }), review({ status: "confirmed" }), review({ bookmark: "yes" }), review({ updatedAt: "bad" }), review({ cell: "20000:10" }), review({ injected: true }), review({ notes: {} })]) assert.throws(() => parseReviews(file([r])));
  assert.throws(() => parseReviews(file([review(), review()])));
  assert.throws(() => parseReviews(file(Array.from({ length: 2001 }, review))));
  assert.throws(() => parseReviews(" ".repeat(MAX_IMPORT_BYTES + 1)));
  assert.throws(() => parseReviews('{"version":1,"reviews":[],"__proto__":{"polluted":true}}'));
  assert.throws(() => parseReviews('{"version":1,"reviews":[{"constructor":{}}]}'));
  assert.throws(() => parseReviews('{"version":1,"reviews":[],"extra":true}'));
  assert.equal({}.polluted, undefined);
});

test("blocked storage reads and writes return explicit failure and never overwrite on read", () => {
  let writes = 0;
  const corrupt = { getItem: () => "{corrupt", setItem: () => { writes++; } };
  assert.match(readReviews(corrupt).error, /not overwritten/); assert.equal(writes, 0);
  const denied = { getItem: () => { throw new Error("denied"); }, setItem: () => { throw new Error("quota"); } };
  assert.match(readReviews(denied).error, /denied/);
  const result = writeReviews(denied, new Map([[review().cell, review()]]));
  assert.equal(result.ok, false); assert.match(result.error, /Not saved.*quota/);
});

test("CSV escapes quotes, newlines and formula prefixes, JSON snapshot carries provenance and reviews", () => {
  for (const value of ["=1+1", "+SUM(A1)", "-1+1", "@SUM(A1)", " \t=cmd", "\ttext", "\ntext"]) assert.match(csvCell(value), /^"'/);
  assert.equal(csvCell('a,"b"\r\nc'), '"a,""b""\r\nc"');
  const e = mergeFeeds([feed("national", [event()])])[0];
  const reviews = new Map([[cellKey(e), review({ notes: '=HYPERLINK("bad")' })]]);
  const snapshot = reportSnapshot([e], reviews, "india", "2026-10-03T00:00:00Z");
  e.provenance.source = "changed"; reviews.get(cellKey(e)).notes = "changed";
  const restored = JSON.parse(JSON.stringify(snapshot));
  assert.equal(restored.cases[0].event.provenance.source, "firms_live");
  assert.match(reportCsv(snapshot), /'=HYPERLINK/);
  assert.match(restored.caveat, /not shared evidence or ground truth/);
});
