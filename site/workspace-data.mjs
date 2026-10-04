import { inRegion } from "./regions.mjs";

export const WORKSPACE_FEEDS = [
  { id: "india", url: "globe/data/events.json" },
  { id: "global", url: "globe/data/global-events.json" },
];

export async function loadWorkspace(fetcher = globalThis.fetch.bind(globalThis)) {
  const results = await Promise.allSettled(WORKSPACE_FEEDS.map(async (feed) => {
    const response = await fetcher(feed.url, { cache: "no-cache", signal: AbortSignal.timeout(20000) });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    if (!Array.isArray(data?.events) || data.meta?.scope !== feed.id ||
        !["firms_live", "local_cache", "mixed"].includes(data.meta?.source)) throw new Error("Unsupported snapshot");
    return { ...feed, data };
  }));
  const feeds = {}, failures = [];
  results.forEach((result, index) => {
    if (result.status === "fulfilled") feeds[result.value.id] = result.value.data;
    else failures.push({ id: WORKSPACE_FEEDS[index].id, error: String(result.reason?.message ?? result.reason) });
  });
  if (!Object.keys(feeds).length) throw new Error("No published snapshots available");
  return { feeds, failures };
}

export function scopedWorkspace(workspace, region) {
  const preferIndia = ["india", "jharkhand-odisha"].includes(region.id);
  const preferred = preferIndia ? "india" : "global";
  const source = workspace.feeds[preferred] ?? workspace.feeds[preferIndia ? "global" : "india"];
  const events = source.events.filter((event) => inRegion(event, region.id));
  const dates = events.map((event) => event.acqDate).filter((date) => /^\d{4}-\d{2}-\d{2}$/.test(date ?? "")).sort();
  const meta = { ...source.meta, events: events.length, observations: undefined,
    persistentSources: undefined, statesWithActivity: undefined, satellites: undefined,
    observationStart: dates[0], observationEnd: dates.at(-1) };
  const stale = Number.isFinite(Date.parse(meta.generatedAt)) && Date.now() - Date.parse(meta.generatedAt) > 12 * 3600000;
  const coverage = `${source.meta.scope === "global" ? "Global" : "India"} snapshot${meta.partial ? " / partial export" : ""}${stale ? " / stale dataset" : ""}${!workspace.feeds[preferred] ? " / requested feed unavailable" : ""}`;
  return { data: { ...source, meta, events }, coverage };
}
