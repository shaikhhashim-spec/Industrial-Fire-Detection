import { CATEGORY_COLORS, RISK_COLORS, type ThermalEvent } from "@/lib/thermal";

function Sparkline({ values, color }: { values: number[]; color: string }) {
  const max = Math.max(...values, 1);
  const pts = values
    .map((v, i) => `${(i / Math.max(1, values.length - 1)) * 100},${32 - (v / max) * 30}`)
    .join(" ");
  return (
    <svg viewBox="0 0 100 32" preserveAspectRatio="none" className="h-10 w-full">
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.6} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-border/60 py-1.5">
      <span className="mono-label">{k}</span>
      <span className="font-mono text-xs text-foreground">{v}</span>
    </div>
  );
}

export function EventDetail({ event }: { event: ThermalEvent | null }) {
  if (!event) {
    return (
      <div className="panel flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
        <p className="mono-label">No event selected</p>
        <p className="max-w-[22ch] text-sm text-muted-foreground">
          Click a thermal beam on the globe to open its investigation record.
        </p>
      </div>
    );
  }

  const risk = RISK_COLORS[event.riskLevel];
  return (
    <div className="panel flex h-full flex-col gap-4 overflow-y-auto p-4">
      <div>
        <div className="flex items-center justify-between">
          <span className="font-mono text-sm text-foreground">{event.id}</span>
          <span
            className="rounded-sm px-2 py-0.5 font-mono text-[0.62rem] tracking-widest"
            style={{ background: `${risk}22`, color: risk, border: `1px solid ${risk}55` }}
          >
            {event.status}
          </span>
        </div>
        <h2 className="mt-1 text-lg leading-tight font-semibold">{event.region}</h2>
        <span
          className="mt-2 inline-block rounded-sm px-2 py-0.5 text-[0.68rem]"
          style={{
            background: `${CATEGORY_COLORS[event.category]}1f`,
            color: CATEGORY_COLORS[event.category],
            border: `1px solid ${CATEGORY_COLORS[event.category]}55`,
          }}
        >
          {event.category}
        </span>
      </div>

      <div>
        <div className="flex items-end justify-between">
          <span className="mono-label">Risk score</span>
          <span className="font-mono text-2xl" style={{ color: risk }}>
            {event.riskScore}
            <span className="text-sm text-muted-foreground">/100</span>
          </span>
        </div>
        <div className="mt-2 h-1.5 w-full rounded-full bg-muted">
          <div
            className="h-full rounded-full transition-all"
            style={{ width: `${event.riskScore}%`, background: risk }}
          />
        </div>
      </div>

      <div>
        <span className="mono-label">FRP trend (MW)</span>
        <Sparkline values={event.history.map((h) => h.frp)} color={CATEGORY_COLORS[event.category]} />
      </div>

      <div>
        <Row k="Coordinates" v={`${event.latitude.toFixed(4)}, ${event.longitude.toFixed(4)}`} />
        <Row k="FRP" v={`${event.frp.toFixed(1)} MW`} />
        <Row k="Brightness" v={`${event.brightness} K`} />
        <Row k="Confidence" v={`${event.confidence}`} />
        <Row k="Persistence" v={`${event.persistenceDays} days`} />
        <Row k="Detections" v={`${event.detectionCount}`} />
        <Row k="Satellite" v={event.satellite} />
        <Row k="Overpass" v={event.daynight === "N" ? "Night" : "Day"} />
        <Row k="Last acquisition" v={event.acqDate} />
      </div>

      <p className="text-[0.68rem] leading-relaxed text-muted-foreground">
        Satellite detection is not ground truth. Risk and category are AI-assisted prioritization
        signals and require field verification before any operational response.
      </p>
    </div>
  );
}
