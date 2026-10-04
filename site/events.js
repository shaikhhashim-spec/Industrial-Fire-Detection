/*
 * The public Events page: one row per detected event, in the same columns
 * the dashboard's Events table shows (events.mjs), sortable by clicking a
 * column and searchable — client-side, since the whole live run already sits
 * in the browser as events.json.
 */
import { h, num } from "./dom.mjs";
import { mountNav } from "./nav.mjs";
import { ICON } from "./icons.mjs";
import { bootWorkspace } from "./page.mjs";
import { browserPreferences } from "./preferences.mjs";
import { COLUMNS, filterEventRows, formatCell, sortRows, toCsv, toRows } from "./events.mjs";
import { RISK_COLORS } from "./overview.mjs";

const PAGE_SIZE = browserPreferences().pageSize;

mountNav("events.html");

function headerCell(col, sort, onSort) {
  const active = sort.key === col.key;
  return h(
    "th",
    { "aria-sort": active ? (sort.dir === "asc" ? "ascending" : "descending") : "none" },
    h(
      "button",
      { type: "button", onclick: () => onSort(col.key) },
      col.label,
      active && h("span", { class: "dir", "aria-hidden": "true" }, sort.dir === "asc" ? "▲" : "▼"),
    ),
  );
}

function bodyCell(col, row, region) {
  const value = row[col.key];
  if (col.key === "riskLevel") {
    return h(
      "td",
      { "data-label": col.label },
      h("i", { class: "mark", style: `--mark:${RISK_COLORS[value] ?? "#71808f"}` }),
      ` ${value}`,
    );
  }
  return h(
    "td",
    { class: col.numeric ? "num" : col.key === "id" ? "id" : null, "data-label": col.label },
    col.key === "id"
      ? h("a", { href: `investigations.html?${new URLSearchParams({ region, event: String(value) })}` }, formatCell(col, value))
      : formatCell(col, value),
  );
}

function main(data, selectedRegion) {
  const allRows = toRows(data.events);
  const region = selectedRegion.id;
  const search = document.querySelector("#search");
  search.value = new URLSearchParams(location.search).get("q") ?? search.value;
  const state = { query: search.value, sortKey: "riskScore", sortDir: "desc", pageSize: PAGE_SIZE, filters: {} };
  const table = h("table", {});
  const rowcount = h("p", { class: "rowcount", role: "status", "aria-live": "polite" });
  const more = h(
    "div",
    { class: "more" },
    h(
      "button",
      {
        class: "btn",
        type: "button",
        onclick: () => {
          state.pageSize += PAGE_SIZE;
          render();
        },
      },
      `Show ${PAGE_SIZE} more`,
    ),
  );

  function onSort(key) {
    if (state.sortKey === key) state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
    else {
      state.sortKey = key;
      state.sortDir = COLUMNS.find((c) => c.key === key)?.numeric ? "desc" : "asc";
    }
    render();
  }

  function render() {
    const filtered = filterEventRows(allRows, state.query, state.filters);
    const sorted = sortRows(filtered, state.sortKey, state.sortDir);
    const shown = sorted.slice(0, state.pageSize);

    table.replaceChildren(
      h("thead", {}, h("tr", {}, COLUMNS.map((c) => headerCell(c, { key: state.sortKey, dir: state.sortDir }, onSort)))),
      h("tbody", {}, shown.length
        ? shown.map((row) => h("tr", {}, COLUMNS.map((c) => bodyCell(c, row, region))))
        : h("tr", {}, h("td", { colspan: COLUMNS.length, class: "empty" }, "No matching events."))),
    );
    rowcount.textContent =
      filtered.length === allRows.length
        ? `${num(sorted.length)} events, showing ${num(shown.length)}.`
        : `${num(filtered.length)} of ${num(allRows.length)} events match, showing ${num(shown.length)}.`;
    more.hidden = shown.length >= sorted.length;
  }

  const controls = h("div", { class: "workspace-settings", "aria-label": "Event filters" });
  for (const [id, label, choices] of [
    ["risk", "Risk", ["LOW", "MODERATE", "HIGH", "CRITICAL"]],
    ["category", "Category", [...new Set(allRows.map((row) => row.category).filter(Boolean))].sort()],
    ["minDays", "Days active", ["2", "5", "10", "20"]],
  ]) {
    const select = h("select", { class: "select", id: `filter-${id}`, onchange: () => {
      state.filters[id] = select.value;
      state.pageSize = PAGE_SIZE;
      render();
    } }, h("option", { value: "" }, "All"), choices.map((value) => h("option", { value }, id === "minDays" ? `${value}+ days` : value)));
    controls.append(h("label", { class: "field" }, h("span", { class: "field-label" }, label), select));
  }
  document.querySelector("#content").replaceChildren(
    controls,
    h(
      "section",
      { class: "panel" },
      h(
        "div",
        { class: "sec-head" },
        h(
          "div",
          { class: "sec-head-left" },
          h("i", { class: "sec-icon" }, ICON.events()),
          h("div", { class: "sec-hdr" }, `${num(allRows.length)} events`),
        ),
      ),
      h("div", { class: "table-wrap" }, table),
      rowcount,
      more,
    ),
  );
  render();

  document.querySelector("#search").oninput = (e) => {
    state.query = e.target.value;
    state.pageSize = PAGE_SIZE;
    render();
  };
  document.querySelector("#export-btn").onclick = () => {
    const rows = sortRows(filterEventRows(allRows, state.query, state.filters), state.sortKey, state.sortDir);
    const blob = new Blob([toCsv(rows)], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = h("a", { href: url, download: "events.csv" });
    document.body.append(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };
}

bootWorkspace(main);
