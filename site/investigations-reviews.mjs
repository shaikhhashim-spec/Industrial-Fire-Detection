export const STORAGE_KEY = "thermal-investigations-reviews-v1";
export const STATUSES = ["unreviewed", "in-review", "needs-verification", "reviewed"];
export const MAX_IMPORT_BYTES = 2 * 1024 * 1024;
export const MAX_REVIEWS = 2000;
const object = (v) => v && typeof v === "object" && !Array.isArray(v) && Object.getPrototypeOf(v) === Object.prototype;
const fields = (v, allowed) => object(v) && Object.keys(v).every((k) => allowed.includes(k));
const text = (v, max) => typeof v === "string" && v.length <= max;
const timestamp = (v) => text(v, 40) && /^\d{4}-\d{2}-\d{2}T/.test(v) && Number.isFinite(Date.parse(v));

export function validateReview(row) {
  if (!fields(row, ["cell", "eventId", "status", "notes", "bookmark", "updatedAt"]) ||
      !text(row.cell, 32) || !/^-?\d{1,5}:-?\d{1,5}$/.test(row.cell) ||
      !text(row.eventId, 160) || !row.eventId || !STATUSES.includes(row.status) ||
      !text(row.notes, 10000) || typeof row.bookmark !== "boolean" || !timestamp(row.updatedAt)) {
    throw new Error("Invalid review: expected cell, eventId, status, notes (up to 10,000 characters), bookmark and ISO timestamp");
  }
  const [lon, lat] = row.cell.split(":").map(Number);
  if (lon < -18000 || lon > 18000 || lat < -9000 || lat > 9000) throw new Error("Invalid review cell");
  return { cell: row.cell, eventId: row.eventId, status: row.status, notes: row.notes, bookmark: row.bookmark, updatedAt: row.updatedAt };
}

export function parseReviews(raw) {
  if (typeof raw !== "string" || new TextEncoder().encode(raw).length > MAX_IMPORT_BYTES) throw new Error("Review import exceeds 2 MiB");
  const data = JSON.parse(raw, (key, value) => {
    if (["__proto__", "prototype", "constructor"].includes(key)) throw new Error("Forbidden object key in review import");
    return value;
  });
  if (!fields(data, ["version", "reviews"]) || data.version !== 1 || !Array.isArray(data.reviews) || data.reviews.length > MAX_REVIEWS) {
    throw new Error("Expected review file version 1 with at most 2,000 reviews");
  }
  const seen = new Set();
  return data.reviews.map((r) => {
    const row = validateReview(r);
    if (seen.has(row.cell)) throw new Error("Duplicate cell in review import");
    seen.add(row.cell); return row;
  });
}

export function serializeReviews(reviews) {
  const rows = [...reviews.values()].map(validateReview);
  const raw = JSON.stringify({ version: 1, reviews: rows }, null, 2);
  parseReviews(raw);
  return raw;
}

export function readReviews(storage) {
  try {
    const raw = storage.getItem(STORAGE_KEY);
    return { reviews: new Map((raw ? parseReviews(raw) : []).map((r) => [r.cell, r])), error: null };
  } catch (error) { return { reviews: new Map(), error: `Local reviews unavailable: ${error.message}. Existing storage was not overwritten.` }; }
}

export function writeReviews(storage, reviews) {
  try { storage.setItem(STORAGE_KEY, serializeReviews(reviews)); return { ok: true }; }
  catch (error) { return { ok: false, error: `Not saved to this browser: ${error.message}. Keep this page open and export your drafts.` }; }
}

export function mergeReviews(existing, imported) {
  const merged = new Map(existing);
  for (const raw of imported) {
    const row = validateReview(raw), previous = merged.get(row.cell);
    if (!previous || Date.parse(row.updatedAt) > Date.parse(previous.updatedAt)) merged.set(row.cell, row);
  }
  if (merged.size > MAX_REVIEWS) throw new Error("Merged reviews exceed 2,000 cells");
  serializeReviews(merged);
  return merged;
}
