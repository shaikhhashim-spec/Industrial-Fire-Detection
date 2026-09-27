/*
 * The public Overview page: the dashboard's Overview screen, drawn from the live
 * events.json the 3D globe reads (refreshed every six hours by the deploy). The
 * figures come from overview.mjs. Everything from the data goes in as text, never
 * as markup.
 */
import { h, num } from "./dom.mjs";
import { mountNav } from "./nav.mjs";
import { boot } from "./page.mjs";
import { alertCard } from "./alerts-view.mjs";
import { ACCENT, PERSISTENT_COLOR, RISK_COLORS, alertsFrom, matchAlerts, summarize } from "./overview.mjs";

const TOP = 3;
const SEARCH_PAGE = 10;

mountNav("./");

function tile(label, value, color) {
  return h(
    "div",
    { class: "stat", style: color ? `--stat-accent:${color}` : null },
    h("div", { class: "lbl" }, color && h("i", { class: "mark", style: `--mark:${color}` }), label),
    h("div", { class: "val" }, value),
  );
}

function main(data) {
  const summary = summarize(data);
  const alerts = alertsFrom(data.events);
  const meta = data.meta ?? {};
  const hasAttribution = Array.isArray(meta.attribution) && meta.attribution.length > 0;
  const state = { query: "", pageSize: SEARCH_PAGE };

  document.querySelector("#alerts-count").textContent = `Alerts (${summary.critical})`;

  const alertsPanel = h("section", { class: "panel", id: "top-alerts", "aria-label": "Top alerts" });

  function renderAlerts() {
    const searching = state.query.trim() !== "";
    const pool = searching ? matchAlerts(alerts, state.query) : alerts;
    const limit = searching ? state.pageSize : TOP;
    const shown = pool.slice(0, limit);

    const head = h(
      "div",
      { class: "sec-head" },
      h("div", { class: "sec-hdr" }, searching ? "Matching alerts" : "Top alerts"),
      h("a", { class: "btn", href: "alerts.html" }, `All ${num(alerts.length)} alerts →`),
    );

    const list = h("div", {});
    if (searching) list.append(h("p", { class: "count-note" }, `${num(pool.length)} match${pool.length === 1 ? "" : "es"} among the ${num(alerts.length)} alerts.`));
    if (!shown.length) {
      list.append(h("p", { class: "empty" }, searching ? "No alert matches that search." : "No high or critical alerts in this run."));
    }
    for (const alert of shown) list.append(...alertCard(alert));

    const more = pool.length - shown.length;
    if (searching && more > 0) {
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
                state.pageSize += SEARCH_PAGE;
                renderAlerts();
              },
            },
            `Show ${num(Math.min(more, SEARCH_PAGE))} more`,
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
    state.pageSize = SEARCH_PAGE;
    renderAlerts();
  });
  document.querySelector("#alerts-btn").addEventListener("click", () => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    alertsPanel.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
  });
}

boot(main);
