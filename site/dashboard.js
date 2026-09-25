/*
 * The public Overview page: the dashboard's Overview screen, drawn from the live
 * events.json the 3D globe reads (refreshed every six hours by the deploy). The
 * figures come from overview.mjs. Everything from the data goes in as text, never
 * as markup.
 */
import {
  ACCENT,
  PERSISTENT_COLOR,
  RISK_COLORS,
  alertsFrom,
  fmtAge,
  fmtUpdated,
  matchAlerts,
  summarize,
  urgencyColor,
} from "./overview.mjs";

const DATA_URL = "globe/data/events.json";
const TOP = 3;
const FIRST_PAGE = 25;
const SEARCH_LIMIT = 10;

function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value == null || value === false) continue;
    if (key === "class") el.className = value;
    else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else el.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    el.append(typeof child === "object" ? child : document.createTextNode(String(child)));
  }
  return el;
}

const num = (n) => n.toLocaleString("en-US");
const capital = (s) => s.charAt(0) + s.slice(1).toLowerCase();

function tile(label, value, color) {
  return h(
    "div",
    { class: "stat", style: color ? `--stat-accent:${color}` : null },
    h("div", { class: "lbl" }, color && h("i", { class: "mark", style: `--mark:${color}` }), label),
    h("div", { class: "val" }, value),
  );
}

function explainer(alert) {
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

function alertCard(alert) {
  const days = alert.days;
  const facts = [
    ["Risk", `${Math.round(alert.riskScore)}/100`],
    ["Location", `${alert.latitude.toFixed(3)}, ${alert.longitude.toFixed(3)}`],
    ["Active", `${days} day${days === 1 ? "" : "s"}`],
    ["Peak FRP", `${alert.frp.toFixed(1)} MW`],
  ];
  return [
    h(
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
    ),
    h(
      "details",
      { class: "explain" },
      h("summary", {}, "Why it is risky and what to do"),
      // built when opened, so a long list stays light
      h("div", { "data-lazy": "" }),
    ),
  ];
}

function main(data) {
  const summary = summarize(data);
  const alerts = alertsFrom(data.events);
  const meta = data.meta ?? {};
  const hasAttribution = Array.isArray(meta.attribution) && meta.attribution.length > 0;
  const state = { query: "", expanded: false, pageSize: FIRST_PAGE };

  const stored = meta.source && meta.source !== "firms_live" && meta.source !== "mixed";
  document.querySelector("#meta").replaceChildren(
    stored ? "Stored live run" : "Live NASA FIRMS",
    h("br"),
    "Updated ",
    h("span", { class: "v", title: meta.generatedAt }, meta.generatedAt ? `${fmtUpdated(meta.generatedAt)} IST` : "never"),
    meta.generatedAt && h("br"),
    meta.generatedAt && fmtAge(meta.generatedAt),
  );
  document.querySelector("#alerts-count").textContent = `Alerts (${summary.critical})`;

  const alertsPanel = h("section", { class: "panel", id: "top-alerts", "aria-label": "Top alerts" });

  function renderAlerts() {
    const searching = state.query.trim() !== "";
    const pool = searching ? matchAlerts(alerts, state.query) : alerts;
    const limit = searching ? SEARCH_LIMIT * Math.ceil(state.pageSize / FIRST_PAGE) : state.expanded ? state.pageSize : TOP;
    const shown = pool.slice(0, limit);

    const head = h(
      "div",
      { class: "sec-head" },
      h("div", { class: "sec-hdr" }, searching ? "Matching alerts" : "Top alerts"),
      !searching &&
        h(
          "button",
          {
            class: "btn",
            type: "button",
            onclick: () => {
              state.expanded = !state.expanded;
              state.pageSize = FIRST_PAGE;
              renderAlerts();
            },
          },
          state.expanded ? "Show top 3" : "View all alerts",
        ),
    );

    const list = h("div", {});
    if (searching) list.append(h("p", { class: "count-note" }, `${num(pool.length)} match${pool.length === 1 ? "" : "es"} among the ${num(alerts.length)} alerts.`));
    if (!shown.length) {
      list.append(h("p", { class: "empty" }, searching ? "No alert matches that search." : "No high or critical alerts in this run."));
    }
    for (const alert of shown) {
      const [card, details] = alertCard(alert);
      details.addEventListener("toggle", () => {
        const slot = details.querySelector("[data-lazy]");
        if (details.open && slot) slot.replaceWith(explainer(alert));
      });
      list.append(card, details);
    }

    const more = pool.length - shown.length;
    if ((searching || state.expanded) && more > 0) {
      list.append(
        h(
          "div",
          { class: "more" },
          h(
            "button",
            {
              class: "btn",
              type: "button",
              onclick: () => {
                state.pageSize += FIRST_PAGE;
                renderAlerts();
              },
            },
            `Show ${num(Math.min(more, searching ? SEARCH_LIMIT : FIRST_PAGE))} more`,
          ),
        ),
      );
    }
    alertsPanel.replaceChildren(head, list);
  }
  renderAlerts();

  document.querySelector("#content").replaceChildren(
    h(
      "div",
      { class: "statrow" },
      tile("Satellite hotspots", summary.observations == null ? "n/a" : num(summary.observations)),
      tile("Detected events", num(summary.events)),
      tile("Persistent sources", num(summary.persistent), summary.persistent ? PERSISTENT_COLOR : null),
      tile("At known industrial sites", num(summary.atSites), summary.atSites ? ACCENT : null),
    ),
    h(
      "p",
      { class: "pills" },
      h(
        "span",
        { class: "pill" },
        h("i", { class: "mark", style: `--mark:${summary.critical ? RISK_COLORS.CRITICAL : "#71808f"}` }),
        `${summary.critical} critical`,
      ),
      h("span", {}, `${summary.states} states with activity`),
      h("span", {}, `Satellites: ${summary.satellites.join(", ") || "none"}`),
    ),
    h(
      "div",
      { class: "alertbar" },
      h(
        "span",
        { class: "txt" },
        h("b", {}, num(summary.critical)),
        " critical and ",
        h("b", {}, num(summary.high)),
        " high-priority thermal events are waiting for review.",
      ),
      h("a", { class: "btn", href: "globe/" }, "Open the 3D globe"),
    ),
    alertsPanel,
    h(
      "p",
      { class: "footnote" },
      "Satellite detection is not ground truth. Risk and category are AI-assisted prioritization signals and require field verification before any operational response.",
      hasAttribution && h("br"),
      hasAttribution && `Data: ${meta.attribution.join("; ")}.`,
    ),
  );

  const search = document.querySelector("#search");
  search.addEventListener("input", () => {
    state.query = search.value;
    state.pageSize = FIRST_PAGE;
    renderAlerts();
  });
  document.querySelector("#alerts-btn").addEventListener("click", () => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    alertsPanel.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
  });
}

async function load() {
  const content = document.querySelector("#content");
  try {
    const res = await fetch(DATA_URL, { cache: "no-cache" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    main(await res.json());
  } catch (err) {
    console.warn("Could not read the live data:", err);
    content.replaceChildren(
      h("p", { class: "loading" }, "The live data could not be loaded. "),
      h("button", { class: "btn", type: "button", onclick: () => location.reload() }, "Reload"),
    );
  }
}

load();
