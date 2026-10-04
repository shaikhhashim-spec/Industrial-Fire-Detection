import { mountNav } from "./nav.mjs";
import { h } from "./dom.mjs";
import { ICON } from "./icons.mjs";
import { REGIONS, regionById } from "./regions.mjs";
import { applyRegionBranding } from "./branding.mjs";
import { formatLocation, RISK_COLORS, CATEGORY_COLORS } from "./overview.mjs";
import { compactPlume, evaluateConsensus } from "./consensus.mjs";
import { consensusPanel, explainer } from "./alerts-view.mjs";
import { fetchInvestigations, queryCases, paginateCases, historyRows, cellKey, numeric, globeLink, snapshotFreshness, investigationPriority } from "./investigations-data.mjs";
import { STATUSES, MAX_IMPORT_BYTES, readReviews, writeReviews, parseReviews, serializeReviews, mergeReviews } from "./investigations-reviews.mjs";
import { reportSnapshot, reportCsv } from "./investigations-reports.mjs";
import { assessmentDraft } from "./investigations-reviews.mjs";
import { assessmentEditor, assessmentLabel } from "./investigations-assessment-view.mjs";
import { probeServerReviews, serverReviewPanel, hasServerDrafts } from "./investigations-server-view.mjs";

const $ = (id) => document.getElementById(id);
const labelStatus = (s) => ({ unreviewed: "Unreviewed", "in-review": "In review", "needs-verification": "Needs verification", reviewed: "Reviewed" })[s];
const display = (v, unit = "") => numeric(v) !== null ? `${v}${unit}` : "Unavailable";
const str = (v) => typeof v === "string" && v ? v : "Unavailable";
const list = (values) => h("ul", {}, values.map((v) => h("li", {}, v)));
const facts = (rows) => h("dl", { class: "dossier-facts" }, ...rows.map(([key, value]) => h("div", {}, h("dt", {}, key), h("dd", {}, value))));
const button = (text, icon, action, attrs = {}) => h("button", { class: "btn", type: "button", onclick: action, ...attrs }, icon ? ICON[icon]() : null, text);
let storage;
try { storage = window.localStorage; } catch { storage = null; }
let { reviews, error: storageError } = readReviews(storage);
let storageBlocked = !!storageError;
let events = [], selected = null, activeTab = "Evidence", page = 1, loading = true;
let filtered = [], dirty = false, draft = null, memoryOnly = false;
const params = new URLSearchParams(location.search);
let region = regionById(params.get("region")).id;
let requestedEvent = params.get("event");

mountNav("investigations.html");
$("region").replaceChildren(...REGIONS.map((r) => h("option", { value: r.id }, r.label)));
$("region").value = region;
$("status").append(...STATUSES.map((s) => h("option", { value: s }, labelStatus(s))));
applyRegionBranding(region);
if (storageError) storageNotice(storageError, true);

function storageNotice(message, failure = false) {
  $("storage-status").replaceChildren(h("p", { class: failure ? "notice failure" : "notice" }, message));
}

function download(content, name, type) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const anchor = h("a", { href: url, download: name });
  document.body.append(anchor); anchor.click(); anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function rememberDraft() {
  if (!dirty || !draft || !selected) return true;
  return saveReview();
}

function saveReview() {
  if (!selected || !draft) return true;
  const row = { cell: cellKey(selected), eventId: selected.id, ...draft, updatedAt: new Date().toISOString() };
  const candidate = new Map(reviews); candidate.set(row.cell, row);
  try { serializeReviews(candidate); }
  catch (error) { storageNotice(`Review remains an unsaved draft: ${error.message}`, true); return false; }
  // Preserve malformed stored data until explicit recovery.
  const result = storageBlocked ? { ok: false, error: "Storage could not be read. Export drafts or explicitly recover storage before saving." } : writeReviews(storage, candidate);
  reviews = candidate; dirty = false; memoryOnly = !result.ok;
  storageNotice(result.ok ? `Saved locally at ${row.updatedAt}. This review is not shared.` : result.error, !result.ok);
  $("review-time")?.replaceChildren(`Last local edit: ${row.updatedAt}${result.ok ? " (saved)" : " (memory only)"}`);
  renderQueue(); return result.ok;
}

function filters() {
  return Object.fromEntries([["region", region], ...["search", "severity", "category", "persistence", "status", "sort", "direction"].map((id) => [id, $(id).value]),
    ...["plumes", "bookmarks"].map((id) => [id, $(id).checked])]);
}

function syncUrl(push = false) {
  const url = new URL(location.href); url.searchParams.set("region", region);
  if (selected) url.searchParams.set("event", selected.id); else url.searchParams.delete("event");
  (push ? history.pushState : history.replaceState).call(history, null, "", url);
}

function selectCase(event, push = true) {
  rememberDraft(); if (dirty) return;
  selected = event; requestedEvent = event?.id ?? null;
  const r = event ? reviews.get(cellKey(event)) : null;
  draft = event ? { status: r?.status ?? "unreviewed", notes: r?.notes ?? "", bookmark: r?.bookmark ?? false, ...assessmentDraft(r) } : null;
  dirty = false; syncUrl(push); renderQueue(); renderDossier();
  $("workspace").classList.toggle("show-dossier", !!event);
  if (event && matchMedia("(max-width: 760px)").matches) $("dossier-title")?.focus();
}

function renderQueue() {
  filtered = queryCases(events, filters(), reviews);
  const paginated = paginateCases(filtered, page); page = paginated.page;
  $("case-count").textContent = `${filtered.length.toLocaleString()} cases`;
  $("queue").replaceChildren(...paginated.events.map((e) => {
    const review = reviews.get(cellKey(e)), plume = compactPlume(e.plume), priority = investigationPriority(e);
    return h("button", { type: "button", class: `case-row${selected && cellKey(selected) === cellKey(e) ? " selected" : ""}`,
      "aria-pressed": String(!!selected && cellKey(selected) === cellKey(e)), onclick: () => selectCase(e) },
      h("span", { class: "case-row-top" }, h("b", {}, e.id), h("span", { class: "severity", style: `color:${RISK_COLORS[e.riskLevel] ?? "var(--ink2)"}` }, str(e.riskLevel))),
      h("span", { class: "case-location" }, formatLocation(e)),
      h("span", { class: "case-category", style: `border-color:${CATEGORY_COLORS[e.category] ?? "var(--line)"}` }, str(e.category)),
      h("span", { class: "case-metrics" }, `Risk ${display(e.riskScore)} | ${display(e.persistenceDays, " d")} | ${display(e.frp, " MW")}`),
      h("span", { class: "case-metrics" }, `Thermal change: ${priority.thermal.label}`),
      h("span", { class: "case-metrics", title: priority.contributions.map((c) => `+${c.points}: ${c.reason}`).join("\n") || "No added priority signals." }, `Review priority ${priority.points} pts | ${priority.contributions.map((c) => `${c.label} +${c.points}`).join(" | ") || "No added priority signals"}`),
      h("span", { class: "case-review" }, `${review?.bookmark ? "Bookmarked | " : ""}${labelStatus(review?.status ?? "unreviewed")} | ${e.provenance.feed}${plume ? " | Plume" : ""}`));
  }));
  if (!paginated.events.length) $("queue").append(h("p", { class: "empty" }, loading ? "Loading cases..." : events.length ? "No cases match these filters." : "No available case records in the loaded feeds."));
  $("pagination").replaceChildren(button("Previous", null, () => { page--; renderQueue(); }, { disabled: page <= 1 }),
    h("span", {}, `${page} / ${paginated.pages}`), button("Next", null, () => { page++; renderQueue(); }, { disabled: page >= paginated.pages }));
}

function thermalChangePanel(e, priority = investigationPriority(e)) {
  const t = priority.thermal;
  const signed = (v) => typeof v === "number" && Number.isFinite(v) ? `${v > 0 ? "+" : ""}${v.toFixed(1)}%` : "Unavailable";
  return h("section", { class: "thermal-change", "aria-label": "Thermal Change" },
    h("h3", {}, "Thermal Change"), h("p", {}, t.label), facts([
      ["Baseline FRP", display(t.baselineFrp, " MW")], ["Current-day peak FRP", display(t.currentFrp, " MW")],
      ["Change", signed(t.changePercent)], ["Prior comparable days", display(t.observationDays)],
      ["Days without comparable observations", display(t.gaps)], ["Review priority", `${priority.points} pts`],
    ]), list(t.reasons),
    h("details", {}, h("summary", {}, "Priority reasons and limitations"),
      list(priority.contributions.map((c) => `+${c.points} pts: ${c.reason}`)), list(t.limitations),
      h("p", { class: "caveat-inline" }, priority.caveat)));
}

function provenancePanel(e) {
  const p = e.provenance;
  return h("section", { class: "provenance" }, h("h3", {}, "Source snapshot"), facts([
    ["Dataset", `${p.feed} (${p.scope})`], ["Source", str(p.source)], ["Generated", str(p.generatedAt)],
    ["Current-feed window", display(p.windowDays, " days")], ["Freshness", snapshotFreshness(p.generatedAt).label], ["Coverage", p.partial ? "Partial / sampled" : "Consult feed coverage; absence does not establish no activity"],
    ["History coverage", p.historyScope ?? "Supplied observations only; coverage is not continuous"],
    ["Record", e.id], ["Cell", cellKey(e)],
  ]), h("a", { href: p.url }, "Original feed JSON"), list(p.attribution));
}

function evidencePanel(e) {
  const evidence = e.evidence ?? {}, plume = compactPlume(e.plume), facility = e.facility;
  const data = (key, fallback) => Object.hasOwn(evidence, key) ? evidence[key] : e[fallback];
  return h("div", {}, thermalChangePanel(e), facts([
    ["Location", formatLocation(e)], ["Coordinates", `${e.latitude.toFixed(4)}, ${e.longitude.toFixed(4)}`],
    ["Rule category", str(e.category)], ["Risk score", display(e.riskScore, "/100")],
    ["Peak FRP", display(data("maxFrp", "frp"), " MW")], ["Mean FRP", display(evidence.meanFrp, " MW")],
    ["Days active", display(data("days", "persistenceDays"))], ["Detections", display(data("detections", "detectionCount"))],
    ["Mean confidence", display(data("meanConfidence", "confidence"), "/100")], ["Night passes", display(evidence.nightPasses)],
    ["First seen", str(evidence.firstSeen)], ["Last seen", str(evidence.lastSeen ?? e.acqDate)],
    ["Satellites", (Array.isArray(evidence.satellites) ? evidence.satellites : Array.isArray(e.satellites) ? e.satellites : [e.satellite]).filter((v) => typeof v === "string").join(", ") || "Unavailable"],
  ]), h("h3", {}, "Mapped context"), facility ? facts([
    ["Facility", str(facility.name)], ["Kind", str(facility.kind)], ["Distance", display(facility.distanceKm, " km")],
    ["Source", str(facility.source)], ["Reference", str(facility.ref)],
  ]) : h("p", { class: "empty" }, "Mapped facility and facility distance unavailable in this record."),
    h("p", { class: "caveat-inline" }, "Separate mine, power plant, forest and water distances are unavailable in this export. Mapped proximity does not establish cause."),
    h("h3", {}, "Estimated plume context"), plume ? facts([
      ["Estimate", plume.label], ["Wind speed", `${plume.windSpeedKmh.toFixed(1)} km/h`],
      ["Wind source", str(e.plume.source)], ["Wind timestamp", str(e.plume.observedAt)],
    ]) : h("p", { class: "empty" }, "Valid wind and plume estimate unavailable."),
    h("p", { class: "caveat-inline" }, "Wind estimates are dispersion context, not observed smoke or a scientific spread forecast."),
    h("h3", {}, "Exported rule explanation"), explainer({ riskFactors: Array.isArray(e.riskFactors) ? e.riskFactors : [],
      actions: Array.isArray(e.actions) ? e.actions : [], riskSummary: e.riskSummary, model: e.model,
      reasons: Array.isArray(e.reasons) ? e.reasons.filter((v) => typeof v === "string") : [] }), provenancePanel(e));
}

function historyPanel(e) {
  const rows = historyRows(e);
  if (!rows.length) return h("div", {}, thermalChangePanel(e), h("p", { class: "empty" }, "Observation history unavailable. Summary counts cannot reconstruct daily observations or a baseline."), provenancePanel(e));
  const peak = Math.max(1, ...rows.map((r) => r.frp)), daily = new Map();
  rows.forEach((r) => daily.set(r.date.slice(0, 10), Math.max(daily.get(r.date.slice(0, 10)) ?? 0, r.frp)));
  return h("div", {}, thermalChangePanel(e), h("p", { class: "history-caption" }, `${rows.length} supplied observations${e.historyTruncated ? " (display bounded to 2,000 rows)" : ""}. Daily bars show only the maximum of supplied samples. Missing days are not zero; history may be truncated.`),
    h("figure", { class: "history-chart", "aria-label": "Peak FRP by supplied observation date" },
      [...daily].map(([date, frp]) => h("div", { class: "history-bar-row" }, h("span", {}, date),
        h("span", { class: "history-track" }, h("span", { class: "history-bar", style: `width:${frp / peak * 100}%` })), h("span", {}, `${frp} MW`)))),
    h("div", { class: "history-table-wrap" }, h("table", { class: "history-table" }, h("caption", {}, "Supplied observation history"),
      h("thead", {}, h("tr", {}, ["Date", "FRP (MW)", "Confidence (/100)"].map((v) => h("th", { scope: "col" }, v)))),
      h("tbody", {}, rows.map((row) => h("tr", {}, h("td", {}, row.date), h("td", {}, row.frp), h("td", {}, display(row.confidence))))))), provenancePanel(e));
}

function reviewPanel(e) {
  const status = h("select", { id: "review-status", onchange: () => { draft.status = status.value; markDirty(); } },
    STATUSES.map((s) => h("option", { value: s }, labelStatus(s)))); status.value = draft.status;
  const notes = h("textarea", { id: "review-notes", rows: 10, maxlength: 10000, oninput: () => { draft.notes = notes.value; markDirty(); } }, draft.notes);
  const bookmark = h("input", { id: "review-bookmark", type: "checkbox", onchange: () => { draft.bookmark = bookmark.checked; markDirty(); } }); bookmark.checked = draft.bookmark;
  return h("div", { class: "review-form" }, h("p", { class: "notice" }, "Browser-local review. Personal annotations are not shared, verified evidence or ground truth. No backend account is required."),
    h("label", {}, h("span", {}, "Review status"), status), h("label", { class: "check" }, bookmark, "Bookmark this cell"),
    h("label", {}, h("span", {}, "Analyst notes"), notes),
    assessmentEditor(draft, markDirty, { idPrefix: "local" }),
    h("p", { id: "review-time", class: "review-time" }, reviews.get(cellKey(e)) ? `Last local edit: ${reviews.get(cellKey(e)).updatedAt}` : "No local review saved."),
    button("Save local review", "download", saveReview), button("Export local reviews", "download", exportReviews), serverReviewPanel(e));
}

function markDirty() { dirty = true; $("review-time")?.replaceChildren("Unsaved draft. Save to persist in this browser."); }

function renderDossier() {
  if (!selected) { $("dossier").replaceChildren(h("p", { class: "empty" }, requestedEvent ? `Requested case ${requestedEvent} is unavailable in the selected region or feed snapshots.` : "Select a case to inspect its evidence.")); return; }
  const e = selected;
  const panel = h("div", { id: "dossier-panel", role: "tabpanel", "aria-labelledby": `tab-${activeTab}`, tabindex: 0, class: "dossier-panel" });
  const tabs = h("div", { class: "dossier-tabs", role: "tablist", "aria-label": "Case dossier sections" },
    ["Evidence", "History", "Screening", "Review"].map((name, i, names) => button(name, null, () => {
      rememberDraft(); if (dirty) return;
      activeTab = name; renderDossier(); $(`tab-${name}`).focus();
    }, { id: `tab-${name}`, role: "tab", "aria-selected": String(activeTab === name), "aria-controls": "dossier-panel", tabindex: activeTab === name ? 0 : -1,
      onkeydown: (event) => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        const next = event.key === "Home" ? 0 : event.key === "End" ? 3 : (i + (event.key === "ArrowRight" ? 1 : 3)) % 4;
        $(`tab-${names[next]}`).click();
      } })));
  const link = globeLink(e, region);
  $("dossier").replaceChildren(h("header", { class: "dossier-header" },
    button("Back to queue", null, () => selectCase(null), { class: "btn mobile-back" }),
    h("h2", { id: "dossier-title", tabindex: -1 }, e.id), h("p", {}, formatLocation(e)), h("p", { class: "case-category" }, str(e.category)),
    h("div", { class: "dossier-actions" }, link ? h("a", { class: "btn", href: link }, ICON.globe(), "Inspect 3D") : null,
      button("CSV", "download", () => exportReport("csv", [e])), button("JSON", "download", () => exportReport("json", [e])), button("Print", "list", () => printReport([e])))), tabs, panel);
  panel.append(activeTab === "Evidence" ? evidencePanel(e) : activeTab === "History" ? historyPanel(e) :
    activeTab === "Screening" ? consensusPanel(evaluateConsensus(e)) : reviewPanel(e));
  if (activeTab === "Screening") panel.querySelector("details").open = true;
}

function exportReviews() {
  rememberDraft(); if (dirty) return;
  try { download(serializeReviews(reviews), "investigation-local-reviews.json", "application/json"); }
  catch (error) { storageNotice(error.message, true); }
}

async function importReviews(file) {
  if (!file) return; rememberDraft(); if (dirty) return;
  try {
    if (file.size > MAX_IMPORT_BYTES) throw new Error("Review import exceeds 2 MiB");
    const imported = parseReviews(await file.text()), next = mergeReviews(reviews, imported);
    const result = storageBlocked ? { ok: false, error: "Import is held in memory. Recover storage explicitly to persist it." } : writeReviews(storage, next);
    reviews = next; memoryOnly = !result.ok;
    storageNotice(result.ok ? `Imported ${imported.length} reviews. Newer timestamps win; equal timestamps preserve existing reviews. Saved locally.` : result.error, !result.ok);
    if (selected) { const r = reviews.get(cellKey(selected)); draft = { status: r?.status ?? "unreviewed", notes: r?.notes ?? "", bookmark: r?.bookmark ?? false, ...assessmentDraft(r) }; }
    renderQueue(); renderDossier();
  } catch (error) { storageNotice(`Import rejected: ${error.message}. No imported reviews applied.`, true); }
}

function exportReport(kind, cases = null) {
  rememberDraft(); if (dirty) return;
  const snapshot = reportSnapshot(cases ?? filtered, reviews, region);
  download(kind === "csv" ? reportCsv(snapshot) : JSON.stringify(snapshot, null, 2),
    `investigations-${region}.${kind}`, kind === "csv" ? "text/csv;charset=utf-8" : "application/json");
}

function printReport(cases = null) {
  rememberDraft(); if (dirty) return;
  const sourceCases = cases ?? filtered;
  const snapshot = reportSnapshot(sourceCases, reviews, region);
  $("print-report").replaceChildren(h("h1", {}, "Thermal investigations"), h("p", {}, `${regionById(region).label} | ${snapshot.exportedAt}`),
    h("p", {}, snapshot.caveat), ...snapshot.cases.map(({ event: e, review: r }, i) => h("article", {}, h("h2", {}, e.id),
      facts([["Location", formatLocation(e)], ["Category", str(e.category)], ["Severity", str(e.riskLevel)], ["Peak FRP", display(e.frp, " MW")],
        ["Persistence", display(e.persistenceDays, " days")], ["Local status", labelStatus(r?.status ?? "unreviewed")], ["Local bookmark", r?.bookmark ? "Yes" : "No"], ["Local review timestamp", str(r?.updatedAt)]]),
      thermalChangePanel(e, investigationPriority(sourceCases[i])),
      h("h3", {}, "Analyst assessment"), facts([["Assessment", assessmentLabel(r?.assessment)],
        ["Uncertainty", str(r?.uncertainty)], ["Assessed at", str(r?.assessedAt)]]),
      h("h3", {}, "Supporting sources"), list(r?.supportingSources ?? []),
      h("p", {}, "Analyst assessment is a personal evidence interpretation, separate from workflow status. It is not verified ground truth or a training label."),
      h("p", { class: "print-notes" }, r?.notes ?? "No local notes."), provenancePanel(e))));
  $("print-report").querySelectorAll("details").forEach((details) => { details.open = true; });
  window.print();
}

const importInput = h("input", { type: "file", accept: ".json,application/json", class: "sr-only", id: "import-reviews",
  onchange: () => { importReviews(importInput.files[0]); importInput.value = ""; } });
$("workspace-tools").append(button("Queue CSV", "download", () => exportReport("csv")), button("Queue JSON", "download", () => exportReport("json")),
  button("Print queue", "list", () => printReport()), button("Export reviews", "download", exportReviews),
  button("Import reviews", "download", () => importInput.click()), importInput, button("Reload feeds", "refresh", load),
  button("Recover local storage", "refresh", () => {
    rememberDraft(); const result = writeReviews(storage, reviews);
    if (result.ok) { storageBlocked = false; memoryOnly = false; }
    storageNotice(result.ok ? "Current local reviews saved. Previous unreadable storage has been replaced." : result.error, !result.ok);
  }, { title: "Explicitly replace unreadable review storage with the current in-memory reviews" }));

for (const id of ["search", "severity", "category", "persistence", "status", "sort", "direction", "plumes", "bookmarks"]) {
  $(id).addEventListener(id === "search" ? "input" : "change", () => { page = 1; renderQueue(); });
}
$("region").addEventListener("change", () => {
  rememberDraft(); if (dirty) { $("region").value = region; return; }
  region = $("region").value; selected = null; requestedEvent = null; page = 1;
  $("workspace").classList.remove("show-dossier"); applyRegionBranding(region); syncUrl(true); renderQueue(); renderDossier();
});
$("reset").addEventListener("click", () => {
  for (const id of ["search", "severity", "category", "persistence", "status"]) $(id).value = "";
  $("sort").value = "priority"; $("direction").value = "desc"; $("plumes").checked = $("bookmarks").checked = false;
  page = 1; renderQueue();
});
window.addEventListener("popstate", () => {
  rememberDraft(); if (dirty) { syncUrl(); return; }
  const p = new URLSearchParams(location.search); region = regionById(p.get("region")).id; $("region").value = region;
  requestedEvent = p.get("event"); selected = null; page = 1; applyRegionBranding(region); resolveRequested();
});
window.addEventListener("beforeunload", (e) => { if (dirty || memoryOnly || hasServerDrafts()) { e.preventDefault(); e.returnValue = ""; } });

function resolveRequested() {
  const match = requestedEvent ? queryCases(events, { region }).find((e) => e.id === requestedEvent || e.aliases.includes(requestedEvent)) : null;
  if (match) {
    selectCase(match, false);
    const index = filtered.findIndex((e) => e.id === match.id);
    if (index >= 0) { page = Math.floor(index / 50) + 1; renderQueue(); }
  } else {
    selected = null; $("workspace").classList.remove("show-dossier"); renderQueue(); renderDossier();
    if (requestedEvent) $("feed-status").append(h("p", { class: "notice failure" }, `Requested case ${requestedEvent} is unavailable in this region or feed snapshots.`));
  }
}

async function load() {
  rememberDraft(); if (dirty) return;
  loading = true; $("feed-status").replaceChildren(h("p", { class: "notice" }, "Loading national and global snapshots..."));
  const result = await fetchInvestigations(); events = result.events; loading = false;
  const messages = result.failures.map((f) => `${f.name} feed unavailable: ${f.error}.`);
  result.feeds.forEach((f) => {
    const freshness = snapshotFreshness(f.meta.generatedAt);
    if (freshness.warning) messages.push(`${f.name}: ${freshness.label}`);
    if (f.meta.partial) messages.push(`${f.name} coverage is partial / sampled.`);
    if (f.rejected) messages.push(`${f.name}: ${f.rejected} invalid records omitted.`);
    if (!f.events.length) messages.push(`${f.name}: no case records in this snapshot.`);
  });
  $("feed-status").replaceChildren(h("p", { class: messages.length ? "notice failure" : "notice" }, messages.length ? messages.join(" ") : "National and global snapshots loaded. Satellite classifications require human verification."));
  $("meta").replaceChildren(...result.feeds.map((f) => h("div", {}, `${f.name}: ${str(f.meta.generatedAt)}`)));
  if (!result.feeds.length) $("meta").textContent = "All feeds unavailable";
  const currentCategory = $("category").value;
  $("category").replaceChildren(h("option", { value: "" }, "All categories"), ...[...new Set(events.map((e) => e.category).filter((v) => typeof v === "string"))].sort().map((v) => h("option", { value: v }, v)));
  if ([...$("category").options].some((o) => o.value === currentCategory)) $("category").value = currentCategory;
  resolveRequested();
}

await load();
probeServerReviews().then((available) => {
  if (available && activeTab === "Review" && selected) {
    const panel = serverReviewPanel(selected);
    if (panel) $("dossier-panel").append(panel);
  }
});
