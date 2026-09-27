/*
 * Renders one alert: the card (title, severity, risk/location/active/FRP) and
 * its "why it is risky and what to do" explainer. Shared by the Overview page
 * (top 3) and the Alerts page (everything), so the two never drift apart.
 */
import { h } from "./dom.mjs";
import { RISK_COLORS, urgencyColor } from "./overview.mjs";

const capital = (s) => s.charAt(0) + s.slice(1).toLowerCase();

export function explainer(alert) {
  const body = h("div", { class: "explain-body" });
  if (!alert.riskFactors.length && !alert.actions.length) {
    body.append(h("p", { class: "empty" }, "No risk breakdown for this event."));
  }
  if (alert.riskSummary) body.append(h("p", { class: "risk-lead" }, alert.riskSummary));

  if (alert.riskFactors.length) {
    body.append(
      h(
        "div",
        { class: "factors" },
        alert.riskFactors.map((f) =>
          h(
            "div",
            { class: "factor" },
            h(
              "div",
              { class: "factor-head" },
              h("span", { class: "name" }, f.label),
              h("span", { class: "val" }, f.value),
              h("span", { class: "pts" }, `${Math.round(f.points)} pts`),
            ),
            h("div", { class: "bar" }, h("span", { style: `width:${Math.max(2, Math.round(f.share * 100))}%` })),
            h("div", { class: "why" }, f.detail),
          ),
        ),
      ),
    );
  }

  const m = alert.model;
  if (m) {
    const pct = (x) => `${Math.round(x * 100)}%`;
    const verdict = m.agrees
      ? `The model agrees with the rule label (${pct(m.confidence)} confidence).`
      : `The model would call this “${m.label}” instead (${pct(m.confidence)} confidence), so the rule label leans on something the numbers do not capture. Worth a look.`;
    const held = m.holdoutAgreement ? ` It reproduces the rules on ${pct(m.holdoutAgreement)} of held-out events.` : "";
    body.append(
      h(
        "div",
        { class: "model-note" },
        h("b", {}, "Model check."),
        ` ${verdict}${held}`,
        h("br"),
        h("span", { class: "caveat-inline" }, m.caveat ?? ""),
      ),
    );
  }

  if (alert.actions.length) {
    body.append(
      h(
        "div",
        { class: "actions" },
        h("p", { class: "actions-title" }, "What to do"),
        h(
          "ol",
          {},
          alert.actions.map((a) =>
            h(
              "li",
              {},
              h("span", { class: "urgency", style: `--u:${urgencyColor(a.urgency)}` }, a.urgency),
              h("span", { class: "step" }, a.step),
              h("span", { class: "detail" }, a.detail),
            ),
          ),
        ),
      ),
    );
  }

  if (alert.reasons.length) {
    body.append(
      h("p", { class: "evidence-title" }, "Why this point is here"),
      alert.reasons.map((r) => h("div", { class: "evidence" }, r)),
    );
  }
  return body;
}

/** [card, details] — `details` is the collapsed explainer, built lazily the
 * first time it opens so a long list of alerts stays light. */
export function alertCard(alert) {
  const days = alert.days;
  const facts = [];
  if (alert.priority != null) facts.push(["Priority", `#${alert.priority}`]);
  facts.push(
    ["Risk", `${Math.round(alert.riskScore)}/100`],
    ["Location", `${alert.latitude.toFixed(3)}, ${alert.longitude.toFixed(3)}`],
    ["Active", `${days} day${days === 1 ? "" : "s"}`],
    ["Peak FRP", `${alert.frp.toFixed(1)} MW`],
  );
  const card = h(
    "div",
    { class: "alertcard" },
    h(
      "div",
      { class: "title" },
      h("i", { class: "sev", style: `--sev:${RISK_COLORS[alert.severity]}` }),
      alert.title,
      h("span", { class: "id" }, alert.id),
    ),
    h(
      "div",
      { class: "facts" },
      facts.map(([k, v]) => h("span", { class: "fact" }, h("span", { class: "k" }, k), h("span", { class: "v" }, v))),
    ),
    h("div", { class: "meta" }, `${capital(alert.severity)} severity. ${alert.classification}.`),
  );
  const details = h(
    "details",
    { class: "explain" },
    h("summary", {}, "Why it is risky and what to do"),
    h("div", { "data-lazy": "" }),
  );
  details.addEventListener("toggle", () => {
    const slot = details.querySelector("[data-lazy]");
    if (details.open && slot) slot.replaceWith(explainer(alert));
  });
  return [card, details];
}
