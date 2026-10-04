import { h } from "./dom.mjs";
import { ASSESSMENTS, assessmentDraft } from "./investigations-reviews.mjs";

export const assessmentLabel = (value) => ({ unresolved: "Unresolved", industrial_heat: "Industrial heat",
  suspected_fire: "Suspected fire", agricultural_burning: "Agricultural burning", false_positive: "False positive" })[value] ?? "Unresolved";

export function assessmentEditor(draft, onChange, { idPrefix = "assessment" } = {}) {
  const value = assessmentDraft(draft);
  const changed = () => { draft.assessedAt = new Date().toISOString(); time.textContent = draft.assessedAt; onChange(); };
  const select = h("select", { id: `${idPrefix}-assessment`, onchange: () => { draft.assessment = select.value; changed(); } },
    ASSESSMENTS.map((a) => h("option", { value: a }, assessmentLabel(a)))); select.value = value.assessment;
  const sources = h("textarea", { id: `${idPrefix}-supporting-sources`, rows: 4, maxlength: 16391,
    oninput: () => { draft.supportingSources = sources.value.split(/\r?\n/).map((s) => s.trim()).filter(Boolean); changed(); } }, value.supportingSources.join("\n"));
  const uncertainty = h("textarea", { id: `${idPrefix}-uncertainty`, rows: 3, maxlength: 1000,
    oninput: () => { draft.uncertainty = uncertainty.value; changed(); } }, value.uncertainty);
  const time = h("span", { id: `${idPrefix}-assessed-at` }, value.assessedAt ?? "Not assessed");
  return h("section", { class: "assessment-form" }, h("h3", {}, "Analyst assessment"),
    h("label", {}, "Assessment", select), h("label", {}, "Supporting sources", sources),
    h("label", {}, "Uncertainty", uncertainty), h("p", { class: "review-time" }, "Assessed at: ", time));
}
