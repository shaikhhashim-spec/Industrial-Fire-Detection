/*
 * Renders one alert: the card (title, severity, risk/location/active/FRP) and
 * its "why it is risky and what to do" explainer. Shared by the Overview page
 * (top 3) and the Alerts page (everything), so the two never drift apart.
 */
import { h } from "./dom.mjs";
import { RISK_COLORS, urgencyColor, formatLocation } from "./overview.mjs";
import { compactPlume, validCoordinates } from "./consensus.mjs";

const capital = (s) => s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();

export function consensusPanel(consensus) {
  return h("details", { class: "consensus-panel" },
    h("summary", { class: "consensus-summary" }, "Multi-Agent Arena",
      h("span", {}, ` ${consensus.verdict} | Evidence index ${consensus.index}/100`)),
    h("p", {}, "Rule-based evidence screening. Deterministic rules; no LLMs involved."),
    h("meter", { class: "consensus-meter", min: 0, max: 100, value: consensus.index,
      "aria-label": "Heuristic evidence strength, not probability" }, `${consensus.index}/100`),
    ["sentinel", "skeptic", "arbiter"].map((name) => {
      const role = consensus[name];
      return h("section", { class: "consensus-role" },
        h("h4", {}, `${capital(name)} (${role.points >= 0 ? "+" : ""}${role.points} pts)`),
        h("p", {}, role.summary), h("ul", {}, role.evidence.map((reason) => h("li", {}, reason))));
    }),
    h("ul", { class: "consensus-limitations" }, consensus.limitations.map((reason) => h("li", {}, reason))),
  );
}

export function explainer(alert) {
  const body = h("div", { class: "explain-body" });
  if (alert.consensus) body.append(consensusPanel(alert.consensus));
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
    const pct = (x) => typeof x === "number" && Number.isFinite(x) && x >= 0 && x <= 1 ? `${Math.round(x * 100)}%` : "unavailable";
    const verdict = m.agrees
      ? `The model agrees with the rule label (${pct(m.confidence)} confidence).`
      : `The model would call this “${m.label}” instead (${pct(m.confidence)} confidence), so the rule label leans on something the numbers do not capture. Worth a look.`;
    const held = m.holdoutAgreement != null ? ` It reproduces the rules on ${pct(m.holdoutAgreement)} of held-out events.` : "";
    body.append(
      h(
        "div",
        { class: "model-note" },
        h("b", {}, "Model check."),
        ` ${verdict}${held}`,
        h("br"),
        h("span", { class: "caveat-inline" }, "Model confidence cannot validate correctness. ", m.caveat ?? ""),
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
      ...alert.reasons.map((r) => h("div", { class: "evidence" }, r)),
    );
  }
  return body;
}

/** [card, details] — `details` is the collapsed explainer, built lazily the
 * first time it opens so a long list of alerts stays light. */
export function alertCard(alert, region = "india") {
  const days = alert.days;
  const facts = [];
  if (alert.priority != null) facts.push(["Priority", `#${alert.priority}`]);
  facts.push(
    ["Risk", Number.isFinite(alert.riskScore) ? `${Math.round(alert.riskScore)}/100` : "Unavailable"],
    ["Location", formatLocation(alert)],
    ["Active", `${days} day${days === 1 ? "" : "s"}`],
    ["Peak FRP", Number.isFinite(alert.frp) && alert.frp >= 0 ? `${alert.frp.toFixed(1)} MW` : "Unavailable"],
  );
  if (alert.consensus) facts.push(["Evidence", `${alert.consensus.verdict} | ${alert.consensus.index}/100 index`]);
  const plume = validCoordinates(alert.latitude, alert.longitude) ? compactPlume(alert.plume) : null;
  if (plume) facts.push(["Plume", `${plume.coneLengthKm.toFixed(1)} km (${plume.direction})`]);
  const card = h(
    "div",
    { class: "alertcard", "data-severity": alert.severity },
    h(
      "div",
      { class: "title" },
      h("i", { class: "sev", style: `--sev:${RISK_COLORS[alert.severity]}` }),
      alert.title,
      h("a", { class: "id", href: `investigations.html?${new URLSearchParams({ region, event: alert.id })}` }, alert.id),
    ),
    h(
      "div",
      { class: "facts" },
      facts.map(([k, v]) => h("span", { class: "fact" }, h("span", { class: "k" }, k), h("span", { class: "v" }, v))),
    ),
    h("div", { class: "meta" }, `${capital(alert.severity)} severity. ${alert.classification}.`),
    plume ? h("span", { class: "plume-badge", title: "Estimated dispersion context; not confirmation of smoke or fire." }, `${plume.label} / ${plume.windSpeedKmh.toFixed(0)} km/h wind`) : null,
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
