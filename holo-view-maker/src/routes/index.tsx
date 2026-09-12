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
import { fetchEarthquakes, fetchEonet, type Hazard } from "@/lib/hazards";
import type { FireSat } from "@/lib/satellites";

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
          "Interactive globe of live NASA FIRMS thermal detections inside India, each one explained with open-source context.",
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
              : "text-muted-foreground hover:text-foreground"
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
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Eight classification hues exceed what a scatter can be read by, so risk
  // (four ordered states) is the default colouring, as on the dashboard map.
  const [colorBy, setColorBy] = useState<"category" | "risk">("risk");
  const [spin, setSpin] = useState(true);
  const [minRisk, setMinRisk] = useState(0);
  const [showAllDetections, setShowAllDetections] = useState(false);
  const [active, setActive] = useState<Set<Category>>(new Set(CATEGORIES));
  const [allEvents, setAllEvents] = useState<ThermalEvent[]>(NO_EVENTS);
  const [dataSource, setDataSource] = useState<DataSource>("none");
  const [dataMeta, setDataMeta] = useState<DataMeta | null>(null);
  const [loading, setLoading] = useState(true);
  const [layers, setLayers] = useState<Layers>(DEFAULT_LAYERS);
  const [selectedHazard, setSelectedHazard] = useState<Hazard | null>(null);
  const [helpOpen, setHelpOpen] = useState(false);

  const { set: satSet, feed: tleFeed } = useFireSats();
  const { data: quakes, feed: usgsFeed } = usePolledFeed(fetchEarthquakes, 10 * 60_000);
  const { data: naturalEvents, feed: eonetFeed } = usePolledFeed(fetchEonet, 30 * 60_000);
  const sats = satSet?.sats ?? NO_SATS;

  const toggleLayer = useCallback(
    (key: LayerKey) => setLayers((prev: Layers) => ({ ...prev, [key]: !prev[key] })),
    [],
  );
  const selectEvent = useCallback((id: string) => {
    setSelectedId(id);
    setSelectedHazard(null);
    setSpin(false);
  }, []);
  const selectHazard = useCallback((h: Hazard) => {
    setSelectedHazard(h);
    setSpin(false);
  }, []);
  const stopSpin = useCallback(() => setSpin(false), []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || isTypingTarget(e.target)) return;
      if (e.key === "?") return setHelpOpen((o: boolean) => !o);
      if (e.key === "Escape") {
        setHelpOpen(false);
        setSelectedHazard(null);
        setSelectedId(null);
        return;
      }
      const k = e.key.toLowerCase();
      if (k === "r") return setSpin((s: boolean) => !s);
      const layer = SHORTCUT_TO_LAYER[k];
      if (layer) toggleLayer(layer);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggleLayer]);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchThermalEvents();
      setAllEvents(res.events);
      setDataSource(res.source);
      setDataMeta(res.meta);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // "Corroborated" hides one-pixel, one-pass detections with nothing else
  // backing them (no repeat, no mapped facility) and flagged false positives.
  const corroboratedCount = useMemo(
    () => allEvents.filter((e: ThermalEvent) => e.corroborated !== false).length,
    [allEvents],
  );
  const events = useMemo(
    () =>
      allEvents.filter(
        (e: ThermalEvent) =>
          e.riskScore >= minRisk &&
          active.has(e.category) &&
          (showAllDetections || e.corroborated !== false),
      ),
    [allEvents, minRisk, active, showAllDetections],
  );
  const selected = useMemo(
    () => events.find((e: ThermalEvent) => e.id === selectedId) ?? null,
    [events, selectedId],
  );

  // The card closes with its layer rather than pointing at a hidden marker.
  const shownHazard =
    selectedHazard &&
    ((selectedHazard.kind === "earthquake" && layers.quakes) ||
      (selectedHazard.kind === "eonet" && layers.eonet))
      ? selectedHazard
      : null;

  const eonetCategories = useMemo(() => {
    const byId = new Map<string, { id: string; label: string; count: number }>();
    for (const h of naturalEvents) {
      const c = byId.get(h.category) ?? { id: h.category, label: h.categoryLabel, count: 0 };
      c.count += 1;
      byId.set(h.category, c);
    }
    return [...byId.values()].sort((a, b) => b.count - a.count);
  }, [naturalEvents]);

  const satDetections = useMemo(() => {
    const out: Record<string, number> = {};
    for (const e of allEvents) out[e.satellite] = (out[e.satellite] ?? 0) + 1;
    return out;
  }, [allEvents]);

  const critical = events.filter((e: ThermalEvent) => e.riskLevel === "CRITICAL").length;
  const high = events.filter((e: ThermalEvent) => e.riskLevel === "HIGH").length;
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
    <main className="flex min-h-screen flex-col px-4 pt-4 lg:h-screen lg:overflow-hidden">
      {/* Inside the Streamlit dashboard (?embed=1) the page above already has the
          title, stats and export button, so don't show them twice. */}
      <header
        hidden={embedded}
        className="mb-4 flex flex-wrap items-end justify-between gap-4 border-b border-border pb-3"
      >
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Thermal Intelligence globe</h1>
          <p className="mt-1 flex items-center gap-2 text-[0.76rem] text-muted-foreground">
            <span
              className="size-2 rounded-[2px]"
              style={{ background: dataSource === "live" ? "var(--ok)" : "var(--critical)" }}
            />
            {dataSource === "live"
              ? `Live NASA FIRMS, India, last ${dataMeta?.windowDays ?? 30} days`
              : "No pipeline export found"}
            <button
              onClick={loadData}
              disabled={loading}
              className="rounded-sm border border-border px-1.5 py-0.5 text-[0.7rem] hover:bg-muted"
            >
              {loading ? "Reloading" : "Reload"}
            </button>
          </p>
        </div>
        <div className="flex flex-wrap gap-6">
          {[
            ["Shown", events.length.toLocaleString()],
            ["Critical", critical.toLocaleString()],
            ["High risk", high.toLocaleString()],
            ["Total FRP", `${Math.round(totalFrp).toLocaleString()} MW`],
          ].map(([k, v]) => (
            <div key={k}>
              <p className="field-label">{k}</p>
              <p className="font-mono text-lg tabular-nums">{v}</p>
            </div>
          ))}
        </div>
      </header>

      <div className="grid gap-4 lg:min-h-0 lg:flex-1 lg:grid-cols-[17rem_1fr_20rem]">
        {/* Layers + controls */}
        <aside className="panel flex flex-col gap-4 overflow-y-auto p-4">
          <LayerPanel
            layers={layers}
            onToggle={toggleLayer}
            counts={{
              detections: events.length,
              sats: sats.length,
              // no number until a feed has answered: "0" would read as "none happening"
              quakes: usgsFeed.updatedAt ? quakes.length : undefined,
              eonet: eonetFeed.updatedAt ? naturalEvents.length : undefined,
            }}
            feeds={{ sats: tleFeed, quakes: usgsFeed, eonet: eonetFeed }}
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
                [true, `All ${allEvents.length.toLocaleString()}`],
              ]}
              value={showAllDetections}
              onChange={setShowAllDetections}
            />
            <p className="mt-1.5 text-[0.66rem] leading-snug text-muted-foreground">
              Corroborated means seen more than once, on two or more days, or at a mapped facility.
              One-off single-pixel detections are hidden unless you pick All.
            </p>
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
                  className={`flex items-center gap-2 rounded-sm px-2 py-1 text-left text-[0.72rem] hover:bg-muted ${
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
        </aside>

        {/* Globe */}
        <section className="panel relative min-h-[60vh] overflow-hidden lg:min-h-0">
          <Suspense
            fallback={
              <div className="flex h-full items-center justify-center">
                <p className="field-label">Loading the globe</p>
              </div>
            }
          >
            <GlobeMap
              events={events}
              selectedId={selectedId}
              colorBy={colorBy}
              spin={spin}
              onSelect={selectEvent}
              layers={layers}
              sats={sats}
              quakes={quakes}
              naturalEvents={naturalEvents}
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
                The pipeline has not exported a live NASA FIRMS run yet. Run it from the dashboard,
                or with python scripts/refresh_national_globe.py, then reload.
              </p>
            </div>
          )}
          <p className="pointer-events-none absolute bottom-3 left-4 z-10 text-[0.7rem] text-muted-foreground">
            Drag to rotate, scroll to zoom, right-drag to tilt. Press <span className="kbd">?</span>{" "}
            for shortcuts.
          </p>
        </section>

        {/* Detail + queue */}
        <aside className="flex min-h-0 flex-col gap-4">
          <div className="min-h-[18rem] flex-1">
            <EventDetail event={selected} sats={sats} hazards={[...quakes, ...naturalEvents]} />
          </div>
          <div className="panel max-h-64 overflow-y-auto p-2">
            <p className="field-label px-2 py-1">Priority queue</p>
            {events.slice(0, 12).map((e: ThermalEvent) => (
              <button
                key={e.id}
                onClick={() => setSelectedId(e.id)}
                className={`flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left hover:bg-muted ${
                  e.id === selectedId ? "bg-muted" : ""
                }`}
              >
                <span
                  className="size-2 shrink-0 rounded-[2px]"
                  style={{ background: RISK_COLORS[e.riskLevel] }}
                />
                <span className="font-mono text-[0.66rem] text-muted-foreground">{e.id}</span>
                <span className="truncate text-[0.72rem]">{e.region}</span>
                <span className="ml-auto font-mono text-[0.7rem] tabular-nums">{e.riskScore}</span>
              </button>
            ))}
          </div>
        </aside>
      </div>

      <StatusBar
        pipeline={{ mode: dataSource, count: allEvents.length, loading }}
        usgs={usgsFeed}
        eonet={eonetFeed}
        tle={tleFeed}
        sats={sats}
        onShowHelp={() => setHelpOpen(true)}
      />
      {helpOpen && <ShortcutsHelp onClose={() => setHelpOpen(false)} />}
    </main>
  );
}
