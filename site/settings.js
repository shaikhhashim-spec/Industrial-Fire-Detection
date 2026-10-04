/* Personal preferences and published snapshot controls; no service credentials. */
import { mountNav } from "./nav.mjs";
import { bootWorkspace } from "./page.mjs";
import { h } from "./dom.mjs";
import { REGIONS } from "./regions.mjs";
import { browserPreferences, savePreferences } from "./preferences.mjs";
import { downloadText } from "./download.mjs";
import { ICON } from "./icons.mjs";

mountNav("settings.html");

bootWorkspace((data, region) => {
  const preferences = browserPreferences();
  const defaultRegion = h("select", { id: "default-region", class: "select" }, REGIONS.map((item) => h("option", { value: item.id }, item.label)));
  defaultRegion.value = preferences.region;
  const size = h("select", { id: "page-size", class: "select" }, [50, 100, 250].map((value) => h("option", { value }, String(value))));
  size.value = String(preferences.pageSize);
  const auto = h("input", { id: "auto-reload", type: "checkbox", checked: preferences.autoReload });
  const status = h("p", { role: "status", class: "count-note" });
  const field = (label, control) => h("label", { class: "field" }, h("span", { class: "field-label" }, label), control);
  const save = h("button", { type: "button", class: "btn", onclick: () => {
    let storage;
    try { storage = localStorage; } catch { storage = null; }
    const result = savePreferences(storage, { region: defaultRegion.value, pageSize: Number(size.value), autoReload: auto.checked });
    status.textContent = result.ok ? "Personal preferences saved in this browser." : "Browser storage unavailable; preferences could not be saved.";
  } }, ICON.settings(), "Save preferences");
  const rows = [
    ["Published source", data.meta.source], ["Observation dates", `${data.meta.observationStart ?? "Unavailable"} to ${data.meta.observationEnd ?? "Unavailable"}`],
    ["Exported", data.meta.generatedAt ?? "Unavailable"], ["Events in this region", data.events.length.toLocaleString()],
    ["Satellite refresh", "Scheduled every six hours"], ["Independent incident accuracy", "Pending corroborated reference data"],
  ];
  document.querySelector("#content").replaceChildren(
    h("section", { class: "panel" }, h("h2", { class: "sec-hdr" }, "Personal preferences"),
      h("div", { class: "workspace-settings" }, field("Default region", defaultRegion), field("Events per page", size),
        h("label", { class: "check" }, auto, "Reload published data every five minutes")), save, status),
    h("section", { class: "panel" }, h("h2", { class: "sec-hdr" }, "Published observations"),
      h("div", { class: "kv" }, rows.map(([key, value]) => h("div", { class: "row" }, h("span", { class: "k" }, key), h("span", { class: "v" }, value)))),
      h("div", { class: "workspace-tools" },
        h("button", { class: "btn", type: "button", onclick: () => location.reload() }, ICON.refresh(), "Reload published data"),
        h("button", { class: "btn", type: "button", onclick: () => downloadText(JSON.stringify(data, null, 2), `snapshot-${region.id}.json`) }, ICON.download(), "Download snapshot"))),
    h("section", { class: "panel", id: "alerts" }, h("h2", { class: "sec-hdr" }, "Server services"),
      h("div", { class: "kv" }, ["Shared accounts and reviews", "Manual pipeline execution", "SMS and voice delivery"].map((name) =>
        h("div", { class: "row" }, h("span", { class: "k" }, name), h("span", { class: "v" }, "Hosted backend required"))))),
    h("p", { class: "footnote" }, "NASA FIRMS detections are observations, not confirmed fires. Risk scores and classifications require human verification."),
  );
});
