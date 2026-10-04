import { cellKey } from "./investigations-data.mjs";
import { formatLocation } from "./overview.mjs";

export function reportSnapshot(events, reviews, region, now = new Date().toISOString()) {
  return { version: 1, exportedAt: now, region,
    caveat: "Satellite screening is not a confirmed fire. Browser-local reviews are personal annotations, not shared evidence or ground truth.",
    cases: events.map((event) => ({ event: structuredClone(event), review: structuredClone(reviews.get(cellKey(event)) ?? null) })) };
}

export function csvCell(value) {
  let text = String(value ?? "");
  if (/^[\s\u0000-\u001f]*[=+@-]/.test(text) || /^[\t\r\n]/.test(text)) text = `'${text}`;
  return `"${text.replace(/"/g, '""')}"`;
}

export function reportCsv(snapshot) {
  const columns = ["Event", "Location", "Latitude", "Longitude", "Category", "Severity", "Risk score", "Peak FRP MW", "Days", "Last seen", "Feed", "Source", "Snapshot generated", "Partial", "Review status (local)", "Notes (local)", "Bookmark (local)", "Review timestamp",
    "Thermal change", "Baseline FRP MW", "Current-day comparable peak FRP MW", "Change percent", "Prior comparable days", "Observation gap days", "Thermal limitations", "History coverage",
    "Analyst assessment (not verified truth)", "Assessment sources", "Assessment uncertainty", "Assessment timestamp"];
  const rows = snapshot.cases.map(({ event: e, review: r }) => [e.id, formatLocation(e), e.latitude, e.longitude,
    e.category, e.riskLevel, e.riskScore, e.frp, e.persistenceDays, e.evidence?.lastSeen ?? e.acqDate,
    e.provenance?.feed, e.provenance?.source, e.provenance?.generatedAt, e.provenance?.partial,
    r?.status ?? "unreviewed", r?.notes, r?.bookmark ?? false, r?.updatedAt,
    e.thermalChange?.label, e.thermalChange?.baselineFrp, e.thermalChange?.currentFrp, e.thermalChange?.changePercent,
    e.thermalChange?.observationDays, e.thermalChange?.gaps, e.thermalChange?.limitations?.join("; "), e.provenance?.historyScope,
    r?.assessment ?? "unresolved", r?.supportingSources?.join("; "), r?.uncertainty, r?.assessedAt]);
  return [columns, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n");
}
