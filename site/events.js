/*
 * The public Events page: one row per detected event, in the same columns
 * the dashboard's Events table shows (events.mjs), sortable by clicking a
 * column and searchable — client-side, since the whole live run already sits
 * in the browser as events.json.
 */
import { h, num } from "./dom.mjs";
import { mountNav } from "./nav.mjs";
import { boot } from "./page.mjs";
import { COLUMNS, filterEventRows, formatCell, sortRows, toCsv, toRows } from "./events.mjs";
import { RISK_COLORS } from "./overview.mjs";

const PAGE_SIZE = 100;

mountNav("events.html");

function headerCell(col, sort, onSort) {
  const active = sort.key === col.key;
  return h(
    "th",
    {},
    h(
      "button",
      { type: "button", onclick: () => onSort(col.key) },
      col.label,
      active && h("span", { class: "dir", "aria-hidden": "true" }, sort.dir === "asc" ? "▲" : "▼"),
    ),
  );
}

function bodyCell(col, row) {
  const value = row[col.key];
  if (col.key === "riskLevel") {
    return h(
      "td",
      {},
      h("i", { class: "mark", style: `--mark:${RISK_COLORS[value] ?? "#71808f"}` }),
      ` ${value}`,
    );
  }
  return h("td", { class: col.numeric ? "num" : col.key === "id" ? "id" : null }, formatCell(col, value));
}

function main(data) {
  const allRows = toRows(data.events);
  const state = { query: "", sortKey: "riskScore", sortDir: "desc", pageSize: PAGE_SIZE };
  const table = h("table", {});
  const rowcount = h("p", { class: "rowcount" });
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
    const filtered = filterEventRows(allRows, state.query);
    const sorted = sortRows(filtered, state.sortKey, state.sortDir);
    const shown = sorted.slice(0, state.pageSize);

    table.replaceChildren(
      h("thead", {}, h("tr", {}, COLUMNS.map((c) => headerCell(c, { key: state.sortKey, dir: state.sortDir }, onSort)))),
      h("tbody", {}, shown.map((row) => h("tr", {}, COLUMNS.map((c) => bodyCell(c, row))))),
    );
    rowcount.textContent =
      filtered.length === allRows.length
        ? `${num(sorted.length)} events, showing ${num(shown.length)}.`
        : `${num(filtered.length)} of ${num(allRows.length)} events match, showing ${num(shown.length)}.`;
    more.hidden = shown.length >= sorted.length;
  }

  document.querySelector("#content").replaceChildren(
    h(
      "section",
      { class: "panel" },
      h("div", { class: "sec-head" }, h("div", { class: "sec-hdr" }, `${num(allRows.length)} events`)),
      h("div", { class: "table-wrap" }, table),
      rowcount,
      more,
    ),
  );
  render();

  document.querySelector("#search").addEventListener("input", (e) => {
    state.query = e.target.value;
    state.pageSize = PAGE_SIZE;
    render();
  });
  document.querySelector("#export-btn").addEventListener("click", () => {
    const rows = sortRows(filterEventRows(allRows, state.query), state.sortKey, state.sortDir);
    const blob = new Blob([toCsv(rows)], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = h("a", { href: url, download: "events.csv" });
    document.body.append(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  });
}

boot(main);
