/*
 * The public Analytics page: the same breakdowns as the dashboard's Analytics
 * page (classification, risk, FRP, persistence, states, satellites), each
 * drawn as ranked text rows with a thin bar — see analytics.mjs for how every
 * count and color is worked out.
 */
import { h, num } from "./dom.mjs";
import { mountNav } from "./nav.mjs";
import { ICON } from "./icons.mjs";
import { bootWorkspace } from "./page.mjs";
import {
  categoryCounts,
  frpHistogram,
  persistenceCounts,
  riskCounts,
  satelliteCounts,
  topStates,
} from "./analytics.mjs";

mountNav("analytics.html");

function metricPanel(icon, title, items, caption) {
  const max = Math.max(1, ...items.map((i) => i.count));
  const panel = h(
    "section",
    { class: "panel" },
    h(
      "div",
      { class: "sec-head" },
      h(
        "div",
        { class: "sec-head-left" },
        h("i", { class: "sec-icon" }, ICON[icon]()),
        h("div", { class: "sec-hdr" }, title),
      ),
    ),
    caption && h("p", { class: "count-note" }, caption),
  );
  if (!items.length || items.every((i) => i.count === 0)) {
    panel.append(h("p", { class: "empty" }, "No events in this run."));
    return panel;
  }
  for (const item of items) {
    panel.append(
      h(
        "div",
        { class: "metric" },
        h(
          "div",
          { class: "metric-head" },
          h("i", { class: "mark", style: `--mark:${item.color}` }),
          h("span", {}, item.label),
          h("span", { class: "val" }, num(item.count)),
        ),
        h("div", { class: "bar" }, h("span", { style: `width:${Math.max(2, Math.round((item.count / max) * 100))}%; background:${item.color}` })),
      ),
    );
  }
  return panel;
}

function main(data) {
  const events = data.events ?? [];
  document.querySelector("#content").replaceChildren(
    h(
      "div",
      { class: "grid-2" },
      metricPanel("tag", "Classification distribution", categoryCounts(events)),
      metricPanel("warning", "Risk distribution", riskCounts(events)),
    ),
    h(
      "div",
      { class: "grid-2" },
      metricPanel("pulse", "FRP distribution (MW)", frpHistogram(events)),
      metricPanel("calendar", "Persistence distribution (days active)", persistenceCounts(events)),
    ),
    h(
      "div",
      { class: "grid-2" },
      metricPanel("pin", "Top states by thermal activity", topStates(events, 10)),
      metricPanel("signal", "Detections by satellite", satelliteCounts(events)),
    ),
    h(
      "p",
      { class: "footnote" },
      "Counts reflect exported events inside the selected geographic window. Satellite observations require independent verification.",
    ),
  );
}

bootWorkspace(main);
