import { createFileRoute } from "@tanstack/react-router";
import { lazy, Suspense, useCallback, useEffect, useMemo, useState, type ChangeEvent } from "react";
import {
  CATEGORIES,
  CATEGORY_COLORS,
  RISK_COLORS,
  fetchThermalEvents,
  type Category,
  type DataMeta,
  type DataSource,
  type RiskLevel,
  type ThermalEvent,
} from "@/lib/thermal";
import { EventDetail } from "@/components/EventDetail";
import { LayerPanel } from "@/components/LayerPanel";
import { StatusBar } from "@/components/StatusBar";
import { ShortcutsHelp } from "@/components/ShortcutsHelp";
import { HazardCard } from "@/components/HazardCard";
import { useFireSats, usePolledFeed } from "@/hooks/use-live-feeds";
import { DEFAULT_LAYERS, SHORTCUT_TO_LAYER, type LayerKey, type Layers } from "@/lib/layers";
import { fetchEonet, type Hazard } from "@/lib/hazards";
import type { FireSat } from "@/lib/satellites";
import { viewFromUrl } from "@/lib/view-params";
import { parentPath } from "@/lib/asset-url";
import { REGIONS, coverageLabel, inRegion, regionById, type RegionId } from "@/lib/regions";

const NO_SATS: FireSat[] = [];
const NO_EVENTS: ThermalEvent[] = [];

/** Keys typed into a text field are text, not shortcuts. */
function isTypingTarget(t: EventTarget | null): boolean {
  if (!(t instanceof HTMLElement)) return false;
  if (t.isContentEditable || t.tagName === "TEXTAREA" || t.tagName === "SELECT") return true;
  return (
    t.tagName === "INPUT" &&
    !["range", "checkbox", "radio", "button"].includes((t as HTMLInputElement).type)
  );
}

const GlobeMap = lazy(() =>
  import("@/components/map/GlobeMap").then((m) => ({ default: m.GlobeMap })),
);

export const Route = createFileRoute("/")({
  ssr: false,
  head: () => ({
    meta: [
      { title: "Thermal Intelligence globe" },
      {
        name: "description",
        content:
          "Interactive NASA FIRMS thermal monitoring globe with regional filtering, export coverage and open-source context.",
      },
      { property: "og:title", content: "Thermal Intelligence globe" },
      {
        property: "og:description",
        content:
          "Live satellite thermal detections in 3D: risk scoring, persistence, FRP and category triage.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Index,
});

/** Segmented control. One accent, used only to mark the selection. */
function Segmented<T extends string | boolean>({
  options,
  value,
  onChange,
}: {
  options: readonly (readonly [T, string])[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div className="flex gap-1 rounded-sm bg-muted p-1">
      {options.map(([v, label]) => (
        <button
          key={String(v)}
          onClick={() => onChange(v)}
          aria-pressed={value === v}
          className={`flex-1 rounded-sm px-2 py-1 text-[0.72rem] ${
            value === v
              ? "bg-primary text-primary-foreground"
              : "text-muted-foreground transition-colors duration-150 hover:text-foreground"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function Index() {
  // route is ssr:false, so window is always available here
  const [embedded] = useState(
    () => new URLSearchParams(window.location.search).get("embed") === "1",
  );
  const [automaticScope] = useState(
    () => !new URLSearchParams(window.location.search).has("region") && viewFromUrl() === null,
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [requestedEvent, setRequestedEvent] = useState<string | null>(() =>
    new URLSearchParams(window.location.search).get("event"),
  );
  const [requestedView] = useState(() => viewFromUrl());
  const [linkMessage, setLinkMessage] = useState<string | null>(null);
  // Eight classification hues exceed what a scatter can be read by, so risk
  // (four ordered states) is the default colouring, as on the dashboard map.
  const [colorBy, setColorBy] = useState<"category" | "risk">("risk");
  const [spin, setSpin] = useState(() => viewFromUrl() === null);
  const [minRisk, setMinRisk] = useState(0);
  const [showAllDetections, setShowAllDetections] = useState(
    () => regionById(new URLSearchParams(window.location.search).get("region")).id !== "india",
  );
  const [active, setActive] = useState<Set<Category>>(new Set(CATEGORIES));
  const [allEvents, setAllEvents] = useState<ThermalEvent[]>(NO_EVENTS);
  const [dataSource, setDataSource] = useState<DataSource>("none");
  const [dataMeta, setDataMeta] = useState<DataMeta | null>(null);
  const [loading, setLoading] = useState(true);
  const [layers, setLayers] = useState<Layers>(DEFAULT_LAYERS);
  const [selectedHazard, setSelectedHazard] = useState<Hazard | null>(null);
  const [helpOpen, setHelpOpen] = useState(false);
  const [region, setRegion] = useState<RegionId>(() => {
    const url = new URL(window.location.href);
    url.searchParams.delete("flat");
    window.history.replaceState(null, "", url);
    const initial = regionById(url.searchParams.get("region"));
    if (url.searchParams.has("region") && initial.id !== "global" && !viewFromUrl()) {
      url.searchParams.set("lat", String(initial.center[1]));
      url.searchParams.set("lon", String(initial.center[0]));
      url.searchParams.set("z", String(initial.zoom));
      window.history.replaceState(null, "", url);
    }
    return initial.id;
  });
  const scopedDataset = dataMeta?.datasets?.find(
    (dataset) => dataset.scope.toLowerCase() === (region === "india" ? "india" : "global"),
  );
  const coverage = coverageLabel(scopedDataset ?? dataMeta);
  const generatedAt = scopedDataset?.generatedAt ?? dataMeta?.generatedAt;
  const timestamp =
    generatedAt && Number.isFinite(Date.parse(generatedAt))
      ? new Date(generatedAt).toLocaleString(undefined, {
          timeZone: "UTC",
          dateStyle: "medium",
          timeStyle: "short",
        }) + " UTC"
      : "Timestamp unavailable";
  const ageHours = generatedAt ? (Date.now() - Date.parse(generatedAt)) / 3_600_000 : NaN;
  const changeRegion = useCallback((id: RegionId) => {
    const next = regionById(id);
    const url = new URL(window.location.href);
    url.searchParams.set("region", id);
    url.searchParams.delete("event");
    if (id === "global") {
      for (const key of ["lat", "lon", "z"]) url.searchParams.delete(key);
    } else {
      url.searchParams.set("lat", String(next.center[1]));
      url.searchParams.set("lon", String(next.center[0]));
      url.searchParams.set("z", String(next.zoom));
    }
    window.history.replaceState(null, "", url);
    setSelectedId(null);
    setRequestedEvent(null);
    setLinkMessage(null);
    setSelectedHazard(null);
    setSpin(false);
    setShowAllDetections(id !== "india");
    setRegion(id);
  }, []);

  const { set: satSet, feed: tleFeed } = useFireSats();
  const { data: naturalEvents, feed: eonetFeed } = usePolledFeed(fetchEonet, 30 * 60_000);
  const sats = satSet?.sats ?? NO_SATS;

  const toggleLayer = useCallback(
    (key: LayerKey) => setLayers((prev: Layers) => ({ ...prev, [key]: !prev[key] })),
    [],
  );
  const selectEvent = useCallback((id: string) => {
    const url = new URL(window.location.href);
    url.searchParams.set("event", id);
    window.history.replaceState(null, "", url);
    setSelectedId(id);
    setSelectedHazard(null);
    setSpin(false);
  }, []);
  const selectHazard = useCallback((h: Hazard) => {
    setSelectedHazard(h);
    setSpin(false);
  }, []);
  const stopSpin = useCallback(() => setSpin(false), []);
  const closeEvent = useCallback(() => {
    const url = new URL(window.location.href);
    url.searchParams.delete("event");
    window.history.replaceState(null, "", url);
    setSelectedId(null);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || isTypingTarget(e.target)) return;
      if (e.key === "?") return setHelpOpen((o: boolean) => !o);
      if (e.key === "Escape") {
        setHelpOpen(false);
        setSelectedHazard(null);
        closeEvent();
        return;
      }
      const k = e.key.toLowerCase();
      if (k === "r") return setSpin((s: boolean) => !s);
      const layer = SHORTCUT_TO_LAYER[k];
      if (layer) toggleLayer(layer);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggleLayer, closeEvent]);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchThermalEvents();
      setAllEvents(res.events);
      setDataSource(res.source);
      setDataMeta(res.meta);
      if (
        !embedded &&
        automaticScope &&
        res.meta?.scope?.toLowerCase() === "global" &&
        !new URLSearchParams(window.location.search).has("region")
      ) {
        changeRegion("global");
      }
    } catch (err) {
      // fetchThermalEvents never rejects today (it catches internally and
      // falls back to cached/demo data), but this is called from a bare
      // useEffect and a button onClick with nothing else to catch a regression.
      console.error("Failed to load thermal event data:", err);
    } finally {
      setLoading(false);
    }
  }, [embedded, automaticScope, changeRegion]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    if (loading || !requestedEvent) return;
    const exact = allEvents.find((event) => event.id === requestedEvent);
    const match =
      exact ??
      (requestedView &&
        allEvents.find(
          (event) =>
            Math.floor(event.longitude * 100) === Math.floor(requestedView.center[0] * 100) &&
            Math.floor(event.latitude * 100) === Math.floor(requestedView.center[1] * 100),
        ));
    if (match && inRegion(match.latitude, match.longitude, region)) {
      setShowAllDetections(true);
      selectEvent(match.id);
      if (!exact)
        setLinkMessage("The linked record was replaced by a newer observation in the same cell.");
    } else {
      setLinkMessage("The linked event is not available in this regional snapshot.");
    }
    setRequestedEvent(null);
  }, [loading, requestedEvent, requestedView, allEvents, region, selectEvent]);

  // "Corroborated" hides one-pixel, one-pass detections with nothing else
  // backing them (no repeat, no mapped facility) and flagged false positives.
  const regionalEvents = useMemo(
    () => allEvents.filter((e) => inRegion(e.latitude, e.longitude, region)),
    [allEvents, region],
  );
  const regionalHazards = useMemo(
    () => naturalEvents.filter((h) => inRegion(h.lat, h.lon, region)),
    [naturalEvents, region],
  );
  const corroboratedCount = useMemo(
    () => regionalEvents.filter((e: ThermalEvent) => e.corroborated !== false).length,
    [regionalEvents],
  );
  const events = useMemo(
    () =>
      regionalEvents
        .filter(
          (e: ThermalEvent) =>
            e.riskScore >= minRisk &&
            active.has(e.category) &&
            (showAllDetections || e.corroborated !== false),
        )
        .sort(
          (a, b) =>
            b.riskScore - a.riskScore ||
            (a.priority ?? Infinity) - (b.priority ?? Infinity) ||
            b.frp - a.frp ||
            a.id.localeCompare(b.id),
        ),
    [regionalEvents, minRisk, active, showAllDetections],
  );
  const selected = useMemo(
    () => events.find((e: ThermalEvent) => e.id === selectedId) ?? null,
    [events, selectedId],
  );
  useEffect(() => {
    if (selectedId && window.matchMedia("(max-width: 1023px)").matches) {
      document.querySelector(".console-dossier")?.scrollIntoView({ block: "start" });
    }
  }, [selectedId]);
  useEffect(() => {
    if (selectedId && !selected) setSelectedId(null);
  }, [selectedId, selected]);

  // The card closes with its layer rather than pointing at a hidden marker.
  const shownHazard = selectedHazard && layers.eonet ? selectedHazard : null;

  const eonetCategories = useMemo(() => {
    const byId = new Map<string, { id: string; label: string; count: number }>();
    for (const h of regionalHazards) {
      const c = byId.get(h.category) ?? { id: h.category, label: h.categoryLabel, count: 0 };
      c.count += 1;
      byId.set(h.category, c);
    }
    return [...byId.values()].sort((a, b) => b.count - a.count);
  }, [regionalHazards]);

  const satDetections = useMemo(() => {
    const out: Record<string, number> = {};
    for (const e of regionalEvents) out[e.satellite] = (out[e.satellite] ?? 0) + 1;
    return out;
  }, [regionalEvents]);

  const critical = events.filter((e: ThermalEvent) => e.riskLevel === "CRITICAL").length;
  const criticalIndustrial = events.filter(
    (e) =>
      e.riskLevel === "CRITICAL" &&
      (e.facility || e.category.includes("Industrial")) &&
      !e.category.includes("Non-Industrial"),
  ).length;
  const highWildfire = events.filter(
    (e) =>
      e.category === "Likely Wildfire" && (e.riskLevel === "HIGH" || e.riskLevel === "CRITICAL"),
  ).length;
  const totalFrp = events.reduce((s: number, e: ThermalEvent) => s + e.frp, 0);

  const toggle = (c: Category) => {
    setActive((prev: Set<Category>) => {
      const next = new Set(prev);
      if (next.has(c)) next.delete(c);
      else next.add(c);
      return next;
    });
  };

  return (
    <main className="thermal-console">
      {/* Inside the Streamlit dashboard (?embed=1) the page above already has the
          title, stats and export button, so don't show them twice. */}
      <header hidden={embedded} className="console-header">
        <div>
          <h1 className="text-xl font-semibold">Thermal Intelligence — 3D Planetary Model</h1>
          <p className="mt-1 flex items-center gap-2 text-[0.76rem] text-muted-foreground">
            <span className="size-2 shrink-0 rounded-[2px] bg-accent" />
            Orbital 3D Thermal Detection & Plume Dispersion Engine
            {parentPath() && (
              <span className="flex flex-wrap gap-2" aria-label="Workspace navigation">
                {[
                  ["", "Overview"],
                  ["events.html", "Events"],
                  ["alerts.html", "Alerts"],
                  ["investigations.html", "Investigations"],
                ].map(([path, label]) => (
                  <a
                    key={label}
                    href={`${parentPath() ?? "/"}${path}?${new URLSearchParams({ region, ...(path ? {} : { view: "overview" }) })}`}
                    className="rounded-sm border border-border px-1.5 py-0.5 text-[0.7rem] transition-colors duration-150 hover:bg-muted"
                  >
                    {label}
                  </a>
                ))}
              </span>
            )}
          </p>
        </div>
        <div className="console-metrics" aria-label="Filtered thermal metrics">
          {[
            ["Shown hotspots", events.length.toLocaleString()],
            ["Critical industrial", criticalIndustrial.toLocaleString()],
            ["High-risk wildfire", highWildfire.toLocaleString()],
            [
              "Cell peak FRP sum",
              `${(totalFrp / 1000).toLocaleString(undefined, { maximumFractionDigits: 3 })} GW`,
            ],
          ].map(([k, v]) => (
            <div key={k}>
              <p className="field-label">{k}</p>
              <p className="font-mono text-lg tabular-nums">{v}</p>
            </div>
          ))}
        </div>
      </header>

      <div className="console-scope">
        {linkMessage && (
          <span role="status" className="text-xs text-muted-foreground">
            {linkMessage}
          </span>
        )}
        <span className="text-xs text-muted-foreground">
          {coverage} / {timestamp}
          {dataMeta?.partial ? " / partial export" : ""} / {critical.toLocaleString()} critical
          shown
        </span>
        {ageHours > 12 && (
          <span role="status" className="console-stale">
            Stale feed / {Math.floor(ageHours)} h old / latest export exceeds 12 h
          </span>
        )}
        {dataMeta?.coverage && region !== "india" && (
          <span className="w-full text-xs text-muted-foreground">{dataMeta.coverage}</span>
        )}
      </div>
      <div className="console-workspace">
        {/* Layers + controls */}
        <details className="console-controls" open={window.innerWidth >= 1024}>
          <summary className="text-xs font-semibold">Layers & filters</summary>
          <div className="flex flex-col gap-3 p-3">
            <label className="flex flex-col gap-2 text-xs">
              <span className="field-label">Scope / Region</span>
              <select
                aria-label="Region"
                value={region}
                onChange={(e) => changeRegion(e.target.value as RegionId)}
                className="w-full min-w-0 rounded-sm border border-border bg-background p-2"
              >
                {REGIONS.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.label}
                  </option>
                ))}
              </select>
            </label>
            <LayerPanel
              layers={layers}
              onToggle={toggleLayer}
              counts={{
                detections: events.length,
                sats: sats.length,
                // no number until a feed has answered: "0" would read as "none happening"
                eonet: eonetFeed.updatedAt ? regionalHazards.length : undefined,
                plumes: events.filter((e) => e.plume).length,
              }}
              feeds={{ sats: tleFeed, eonet: eonetFeed }}
              sats={sats}
              satDetections={satDetections}
              eonetCategories={eonetCategories}
              onShowHelp={() => setHelpOpen(true)}
            />

            <p className="-mb-2 border-t border-border pt-3 text-sm font-semibold">Filters</p>
            <div>
              <p className="field-label mb-2">Detections shown</p>
              <Segmented
                options={[
                  [false, `Corroborated ${corroboratedCount.toLocaleString()}`],
                  [true, `All ${regionalEvents.length.toLocaleString()}`],
                ]}
                value={showAllDetections}
                onChange={setShowAllDetections}
              />
            </div>

            <div>
              <p className="field-label mb-2">Colour markers by</p>
              <Segmented
                options={[
                  ["risk", "Risk"],
                  ["category", "Classification"],
                ]}
                value={colorBy}
                onChange={setColorBy}
              />
            </div>

            <div>
              <div className="mb-2 flex justify-between">
                <span className="field-label">Minimum risk</span>
                <span className="font-mono text-xs tabular-nums">{minRisk}</span>
              </div>
              <input
                type="range"
                min={0}
                max={95}
                value={minRisk}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setMinRisk(Number(e.target.value))}
                className="w-full accent-[var(--primary)]"
              />
            </div>

            <label className="flex items-center justify-between">
              <span className="field-label">Auto-rotate</span>
              <span className="flex items-center gap-2">
                <kbd className="kbd">R</kbd>
                <input
                  type="checkbox"
                  checked={spin}
                  onChange={(e: ChangeEvent<HTMLInputElement>) => setSpin(e.target.checked)}
                  className="accent-[var(--primary)]"
                />
              </span>
            </label>

            <div>
              <p className="field-label mb-2">Classification</p>
              <div className="flex flex-col gap-1">
                {CATEGORIES.map((c: Category) => (
                  <button
                    key={c}
                    onClick={() => toggle(c)}
                    aria-pressed={active.has(c)}
                    className={`flex items-center gap-2 rounded-sm px-2 py-1 text-left text-[0.72rem] transition-colors duration-150 hover:bg-muted ${
                      active.has(c) ? "text-foreground" : "text-muted-foreground opacity-45"
                    }`}
                  >
                    <span
                      className="size-2.5 shrink-0 rounded-[2px]"
                      style={{ background: CATEGORY_COLORS[c] }}
                    />
                    {c}
                  </button>
                ))}
              </div>
            </div>

            <div className="mt-auto">
              <p className="field-label mb-2">Risk scale</p>
              <div className="flex flex-col gap-1">
                {(Object.entries(RISK_COLORS) as [RiskLevel, string][]).map(([k, v]) => (
                  <div key={k} className="flex items-center gap-2 text-[0.7rem]">
                    <span className="size-2.5 rounded-[2px]" style={{ background: v }} />
                    {k.charAt(0) + k.slice(1).toLowerCase()}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </details>

        {/* Globe */}
        <section className="console-map" aria-label="Thermal monitoring map">
          <Suspense
            fallback={
              <div className="flex h-full items-center justify-center">
                <p className="field-label">Loading the globe</p>
              </div>
            }
          >
            <GlobeMap
              scope={region}
              events={events}
              selectedId={selectedId}
              colorBy={colorBy}
              spin={spin}
              onSelect={selectEvent}
              layers={layers}
              sats={sats}
              naturalEvents={regionalHazards}
              selectedHazard={shownHazard}
              onSelectHazard={selectHazard}
              onInteract={stopSpin}
            />
          </Suspense>
          {shownHazard && (
            <HazardCard hazard={shownHazard} onClose={() => setSelectedHazard(null)} />
          )}
          {!loading && dataSource !== "live" && (
            <div className="pointer-events-none absolute inset-x-0 top-1/3 z-10 mx-auto max-w-sm rounded-md border border-border bg-card/95 p-4 text-center">
              <p className="text-sm font-semibold">No live detections to show</p>
              <p className="mt-1 text-[0.76rem] text-muted-foreground">
                No thermal dataset is available. NASA EONET and satellite overlays are separate
                feeds.
              </p>
            </div>
          )}
          {!loading && dataSource === "live" && events.length === 0 && (
            <div role="status" className="console-empty">
              <p className="text-sm font-semibold">
                {regionalEvents.length === 0
                  ? "No exported detections in this region"
                  : "No detections match these filters"}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {regionalEvents.length === 0
                  ? `${coverage}. An empty geographic window does not establish absence of fire.`
                  : `${regionalEvents.length.toLocaleString()} detections available in the selected region.`}
              </p>
              {regionalEvents.length > 0 && (
                <button
                  className="mt-2 text-xs text-primary"
                  onClick={() => {
                    setMinRisk(0);
                    setActive(new Set(CATEGORIES));
                    setShowAllDetections(true);
                  }}
                >
                  Reset filters
                </button>
              )}
            </div>
          )}
        </section>

        {/* Detail + queue */}
        <aside className="console-investigation">
          {selected && (
            <div className="console-dossier">
              <EventDetail
                event={selected}
                region={region}
                sats={sats}
                hazards={regionalHazards}
                onClose={closeEvent}
              />
            </div>
          )}
          <div className="console-queue p-2">
            <p className="field-label px-2 py-1">
              Priority queue / {events.length.toLocaleString()} shown
            </p>
            {!events.length && (
              <p className="p-2 text-xs text-muted-foreground">No detections to review.</p>
            )}
            {events.slice(0, 12).map((e: ThermalEvent) => (
              <button
                key={e.id}
                onClick={() => selectEvent(e.id)}
                aria-pressed={e.id === selectedId}
                className={`flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left transition-colors duration-150 hover:bg-muted ${
                  e.id === selectedId ? "bg-muted" : ""
                }`}
              >
                <span
                  className="size-2 shrink-0 rounded-[2px]"
                  style={{ background: RISK_COLORS[e.riskLevel] }}
                />
                <span
                  className="queue-id font-mono text-[0.66rem] text-muted-foreground"
                  title={e.id}
                >
                  {e.id}
                </span>
                <span className="min-w-0 truncate text-[0.72rem]" title={e.region}>
                  {e.region}
                </span>
                <span className="ml-auto shrink-0 font-mono text-[0.7rem] tabular-nums">
                  {e.riskScore}
                </span>
              </button>
            ))}
          </div>
        </aside>
      </div>

      <StatusBar
        pipeline={{ mode: dataSource, count: allEvents.length, loading }}
        eonet={eonetFeed}
        tle={tleFeed}
        sats={sats}
        onShowHelp={() => setHelpOpen(true)}
      />
      {helpOpen && <ShortcutsHelp onClose={() => setHelpOpen(false)} />}
    </main>
  );
}
