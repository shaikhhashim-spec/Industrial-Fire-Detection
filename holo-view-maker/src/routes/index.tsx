import { createFileRoute } from "@tanstack/react-router";
import { lazy, Suspense, useCallback, useEffect, useMemo, useState, type ChangeEvent } from "react";
import {
  CATEGORIES,
  CATEGORY_COLORS,
  RISK_COLORS,
  THERMAL_EVENTS,
  fetchThermalEvents,
  type Category,
  type RiskLevel,
  type ThermalEvent,
} from "@/lib/thermal";
import { EventDetail } from "@/components/EventDetail";


const ThermalGlobe = lazy(() =>
  import("@/components/globe/ThermalGlobe").then((m) => ({ default: m.ThermalGlobe })),
);

export const Route = createFileRoute("/")({
  ssr: false,
  head: () => ({
    meta: [
      { title: "Thermal Intelligence — 3D Fire Risk Globe" },
      {
        name: "description",
        content:
          "Interactive 3D globe for AI-assisted early warning on industrial fires and persistent thermal sources detected from satellite.",
      },
      { property: "og:title", content: "Thermal Intelligence — 3D Fire Risk Globe" },
      {
        property: "og:description",
        content:
          "Explore satellite thermal detections in 3D: risk scoring, persistence, FRP and category triage.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: Index,
});

function Index() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [colorBy, setColorBy] = useState<"category" | "risk">("category");
  const [spin, setSpin] = useState(true);
  const [minRisk, setMinRisk] = useState(0);
  const [active, setActive] = useState<Set<Category>>(new Set(CATEGORIES));
  const [allEvents, setAllEvents] = useState<ThermalEvent[]>(THERMAL_EVENTS);
  const [dataSource, setDataSource] = useState<"live" | "simulation">("simulation");
  const [loading, setLoading] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchThermalEvents();
      if (res.events && res.events.length > 0) {
        setAllEvents(res.events);
        setDataSource(res.source);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const events = useMemo(
    () => allEvents.filter((e: ThermalEvent) => e.riskScore >= minRisk && active.has(e.category)),
    [allEvents, minRisk, active],
  );
  const selected = useMemo(
    () => events.find((e: ThermalEvent) => e.id === selectedId) ?? null,
    [events, selectedId],
  );

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
    <main className="min-h-screen p-4 lg:h-screen lg:overflow-hidden">
      <header className="mb-4 flex flex-wrap items-end justify-between gap-4 border-b border-border pb-3">
        <div>
          <div className="flex items-center gap-2.5">
            <p className="mono-label">SIH26162 · Orbital thermal watch</p>
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[0.63rem] font-mono uppercase tracking-wider ${
                dataSource === "live"
                  ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                  : "bg-amber-500/10 text-amber-400 border border-amber-500/30"
              }`}
            >
              <span
                className={`size-1.5 rounded-full ${
                  dataSource === "live" ? "bg-emerald-400 animate-pulse" : "bg-amber-400"
                }`}
              />
              {dataSource === "live" ? "Live Pipeline Data" : "Simulation Seed"}
            </span>
            <button
              onClick={loadData}
              disabled={loading}
              title="Sync latest pipeline events"
              className="text-muted-foreground hover:text-foreground text-[0.7rem] mono-label font-mono px-1.5 py-0.5 rounded border border-border/70 hover:bg-muted transition-colors"
            >
              {loading ? "Syncing…" : "↻ Sync"}
            </button>
          </div>
          <h1 className="text-xl font-semibold tracking-tight">THERMAL INTELLIGENCE 3D</h1>
        </div>
        <div className="flex flex-wrap gap-5">
          {[
            ["Active events", String(events.length)],
            ["Critical", String(critical)],
            ["High risk", String(high)],
            ["Total FRP", `${totalFrp.toFixed(0)} MW`],
          ].map(([k, v]) => (
            <div key={k}>
              <p className="mono-label">{k}</p>
              <p className="font-mono text-lg">{v}</p>
            </div>
          ))}
        </div>
      </header>


      <div className="grid gap-4 lg:h-[calc(100vh-8.5rem)] lg:grid-cols-[16rem_1fr_20rem]">
        {/* Controls */}
        <aside className="panel flex flex-col gap-4 overflow-y-auto p-4">
          <div>
            <p className="mono-label mb-2">Colour beams by</p>
            <div className="flex gap-1 rounded-sm bg-muted p-1">
              {(["category", "risk"] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => setColorBy(m)}
                  className={`flex-1 rounded-sm px-2 py-1 font-mono text-[0.66rem] tracking-widest uppercase transition-colors ${
                    colorBy === m
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {m}
                </button>
              ))}
            </div>
          </div>

          <div>
            <div className="mb-2 flex justify-between">
              <span className="mono-label">Min risk</span>
              <span className="font-mono text-xs">{minRisk}</span>
            </div>
            <input
              type="range"
              min={0}
              max={95}
              value={minRisk}
              onChange={(e: ChangeEvent<HTMLInputElement>) => setMinRisk(Number(e.target.value))}
              className="w-full accent-[var(--accent)]"
            />
          </div>

          <label className="flex items-center justify-between">
            <span className="mono-label">Auto-rotate</span>
            <input
              type="checkbox"
              checked={spin}
              onChange={(e: ChangeEvent<HTMLInputElement>) => setSpin(e.target.checked)}
              className="accent-[var(--primary)]"
            />
          </label>


          <div>
            <p className="mono-label mb-2">Classification</p>
            <div className="flex flex-col gap-1">
              {CATEGORIES.map((c: Category) => (
                <button
                  key={c}
                  onClick={() => toggle(c)}
                  className={`flex items-center gap-2 rounded-sm px-2 py-1 text-left text-[0.7rem] transition-colors hover:bg-muted ${
                    active.has(c) ? "text-foreground" : "text-muted-foreground opacity-45"
                  }`}
                >
                  <span
                    className="size-2.5 shrink-0 rounded-full"
                    style={{ background: CATEGORY_COLORS[c] }}
                  />
                  {c}
                </button>
              ))}
            </div>
          </div>

          <div className="mt-auto">
            <p className="mono-label mb-2">Risk scale</p>
            <div className="flex flex-col gap-1">
              {(Object.entries(RISK_COLORS) as [RiskLevel, string][]).map(([k, v]) => (
                <div key={k} className="flex items-center gap-2 font-mono text-[0.66rem]">
                  <span className="size-2.5 rounded-sm" style={{ background: v }} />
                  {k}
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
                <p className="mono-label animate-pulse">Initialising orbital view…</p>
              </div>
            }
          >
            <ThermalGlobe
              events={events}
              selectedId={selectedId}
              colorBy={colorBy}
              spin={spin}
              onSelect={(id: string) => {
                setSelectedId(id);
                setSpin(false);
              }}
            />
          </Suspense>
          <p className="pointer-events-none absolute bottom-3 left-4 mono-label">
            Drag to orbit · scroll to zoom · click a beam
          </p>
        </section>

        {/* Detail + queue */}
        <aside className="flex min-h-0 flex-col gap-4">
          <div className="min-h-[18rem] flex-1">
            <EventDetail event={selected} />
          </div>
          <div className="panel max-h-64 overflow-y-auto p-2">
            <p className="mono-label px-2 py-1">Priority queue</p>
            {events.slice(0, 12).map((e: ThermalEvent) => (
              <button
                key={e.id}
                onClick={() => setSelectedId(e.id)}
                className={`flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left transition-colors hover:bg-muted ${
                  e.id === selectedId ? "bg-muted" : ""
                }`}
              >
                <span
                  className="size-2 shrink-0 rounded-full"
                  style={{ background: RISK_COLORS[e.riskLevel] }}
                />
                <span className="font-mono text-[0.66rem] text-muted-foreground">{e.id}</span>
                <span className="truncate text-[0.72rem]">{e.region}</span>
                <span className="ml-auto font-mono text-[0.7rem]">{e.riskScore}</span>
              </button>
            ))}

          </div>
        </aside>
      </div>
    </main>
  );
}
