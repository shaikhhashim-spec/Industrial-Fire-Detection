/*
 * The public Alerts page: every HIGH and CRITICAL event, grouped by severity
 * (critical first) the way the dashboard's Alerts page groups them, each
 * capped with "show more" so a run with hundreds of alerts stays light.
 * Searching flattens the groups into one ranked, matched list.
 */
import { h, num } from "./dom.mjs";
import { mountNav } from "./nav.mjs";
import { ICON } from "./icons.mjs";
import { boot, loadData, renderMeta, renderBranding } from "./page.mjs";
import { REGIONS, inRegion, regionById } from "./regions.mjs";
import { alertCard } from "./alerts-view.mjs";
import { RISK_COLORS, alertsFrom, matchAlerts } from "./overview.mjs";

const TIER_TINT = { CRITICAL: RISK_COLORS.CRITICAL, HIGH: RISK_COLORS.HIGH };

const GROUP_PAGE = 50;
const SEARCH_PAGE = 25;
const TIERS = ["CRITICAL", "HIGH"];

mountNav("alerts.html");

function main(data) {
  const alerts = alertsFrom(data.events);
  const state = { query: "", pageSize: {}, searchPageSize: SEARCH_PAGE };
  for (const tier of TIERS) state.pageSize[tier] = GROUP_PAGE;

  const content = h("div", {});

  function renderSearch() {
    const matches = matchAlerts(alerts, state.query);
    const shown = matches.slice(0, state.searchPageSize);
    const list = h(
      "section",
      { class: "panel" },
      h(
        "div",
        { class: "sec-head" },
        h(
          "div",
          { class: "sec-head-left" },
          h("i", { class: "sec-icon" }, ICON.search()),
          h("div", { class: "sec-hdr" }, "Matching alerts"),
        ),
        h("span", { class: "count-note" }, `${num(matches.length)} of ${num(alerts.length)}`),
      ),
    );
    if (!shown.length) list.append(h("p", { class: "empty" }, "No alert matches that search."));
    for (const alert of shown) list.append(...alertCard(alert));
    if (matches.length > shown.length) {
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
                state.searchPageSize += SEARCH_PAGE;
                render();
              },
            },
            `Show ${num(Math.min(matches.length - shown.length, SEARCH_PAGE))} more`,
          ),
        ),
      );
    }
    content.replaceChildren(list);
  }

  function renderGroups() {
    const panels = TIERS.map((tier) => {
      const group = alerts.filter((a) => a.severity === tier);
      const cap = state.pageSize[tier];
      const shown = group.slice(0, cap);
      const panel = h(
        "section",
        { class: "panel", style: "margin-bottom:1rem" },
        h(
          "div",
          { class: "sec-head" },
          h(
            "div",
            { class: "sec-head-left" },
            h("i", { class: "sec-icon", style: `--tint:${TIER_TINT[tier]}` }, ICON.warning()),
            h("div", { class: "sec-hdr" }, `${tier.charAt(0) + tier.slice(1).toLowerCase()} (${num(group.length)})`),
          ),
        ),
      );
      if (!group.length) {
        panel.append(h("p", { class: "empty" }, `No ${tier.toLowerCase()} alerts in this run.`));
        return panel;
      }
      for (const alert of shown) panel.append(...alertCard(alert));
      if (group.length > shown.length) {
        panel.append(
          h(
            "div",
            { class: "more" },
            h(
              "button",
              {
                class: "btn",
                type: "button",
                onclick: () => {
                  state.pageSize[tier] += GROUP_PAGE;
                  render();
                },
              },
              `Show ${num(Math.min(group.length - shown.length, GROUP_PAGE))} more`,
            ),
          ),
        );
      }
      return panel;
    });
    content.replaceChildren(...panels);
  }

  function render() {
    if (state.query.trim() !== "") renderSearch();
    else renderGroups();
  }
  render();

  document.querySelector("#content").replaceChildren(content);
  document.querySelector("#search").oninput = (e) => {
    state.query = e.target.value;
    state.searchPageSize = SEARCH_PAGE;
    render();
  };
}

boot(async (national) => {
  let global = null;
  try {
    const candidate = await loadData("globe/data/global-events.json");
    if (candidate.meta?.scope === "global" && Array.isArray(candidate.events)) global = candidate;
  } catch { /* National data remains available, with its actual coverage displayed. */ }
  const selector = document.querySelector("#region");
  selector.replaceChildren(...REGIONS.map((region) => h("option", { value: region.id }, region.label)));
  selector.value = regionById(new URLSearchParams(location.search).get("region") ?? (global ? "global" : "india")).id;
  const render = () => {
    const region = regionById(selector.value);
    const source = region.id === "india" || !global ? national : global;
    const url = new URL(location.href);
    url.searchParams.set("region", region.id);
    history.replaceState(null, "", url);
    renderBranding(region.id);
    renderMeta(source.meta ?? {});
    main({ ...source, events: (source.events ?? []).filter((event) => inRegion(event, region.id)) });
    const generated = Date.parse(source.meta?.generatedAt ?? "");
    const scope = source.meta?.scope === "global" ? "Global export" : "India export";
    document.querySelector("#content").prepend(h("p", { class: "scope-note", role: "status" },
      `${region.label} geographic window / ${scope}${source.meta?.partial ? " / partial export" : ""}${Number.isFinite(generated) && Date.now() - generated > 12 * 3600000 ? " / stale dataset" : ""}. Satellite detections require verification.`,
    ));
    const search = document.querySelector("#search");
    if (search.value) search.oninput({ target: search });
  };
  selector.onchange = render;
  render();
});
