import { useMemo } from "react";
import { ExternalLink, Factory, Moon, Sun } from "lucide-react";
import {
  CATEGORY_COLORS,
  RISK_COLORS,
  type RecommendedAction,
  type ThermalEvent,
} from "@/lib/thermal";
import { hazardsNear, type Hazard } from "@/lib/hazards";
import { nextPasses, type FireSat } from "@/lib/satellites";
import { fmtIn, fmtIst, fmtUtc } from "@/lib/format";
import { useNow } from "@/hooks/use-live-feeds";

/** When each FIRMS sensor will next have this hotspot inside its swath — i.e.
 * the next chance of a fresh detection to confirm or clear it. */
function NextOverpasses({ lat, lon, sats }: { lat: number; lon: number; sats: FireSat[] }) {
  const now = useNow(30_000);
  const minute = Math.floor(now.getTime() / 60_000);
  const passes = useMemo(
    () => nextPasses(sats, lat, lon, new Date(minute * 60_000), 24).slice(0, 5),
    [sats, lat, lon, minute],
  );
  if (!sats.length) return null;
  return (
    <div>
      <span className="field-label">Next overpasses, 24 hours</span>
      <div className="mt-1">
        {passes.map((p) => {
          const Icon = p.daylight ? Sun : Moon;
          return (
            <div
              key={`${p.sat.id}-${p.time.getTime()}`}
              className="flex items-center gap-2 border-b border-border/60 py-1 font-mono text-[0.66rem]"
              title={`Closest approach ${Math.round(p.offNadirKm)} km from nadir`}
            >
              <span className="size-2 shrink-0 rounded-[2px]" style={{ background: p.sat.color }} />
              <span className="w-[4.6rem] truncate" style={{ color: p.sat.color }}>
                {p.sat.name}
              </span>
              <span className="text-foreground tabular-nums">{fmtUtc(p.time)}Z</span>
              <span className="text-muted-foreground tabular-nums">{fmtIst(p.time)} IST</span>
              <span className="ml-auto text-muted-foreground">{fmtIn(p.time, now)}</span>
              <Icon aria-hidden className="size-3 shrink-0 text-muted-foreground" />
              <span className="sr-only">{p.daylight ? "daylight pass" : "night pass"}</span>
            </div>
          );
        })}
        {!passes.length && (
          <p className="py-1 text-[0.66rem] text-muted-foreground">No pass in the next 24 h.</p>
        )}
      </div>
    </div>
  );
}

function Sparkline({ values, color }: { values: number[]; color: string }) {
  const max = Math.max(...values, 1);
  const pts = values
    .map((v, i) => `${(i / Math.max(1, values.length - 1)) * 100},${32 - (v / max) * 30}`)
    .join(" ");
  return (
    <svg viewBox="0 0 100 32" preserveAspectRatio="none" className="h-10 w-full">
      <polyline
        points={pts}
        fill="none"
        stroke={color}
        strokeWidth={1.6}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-border/60 py-1.5">
      <span className="field-label">{k}</span>
      <span className="font-mono text-xs text-foreground">{v}</span>
    </div>
  );
}

/** The open-source explanation for a detection: the facility credited for it
 * (with a link to the OSM / WRI record) and the evidence behind the category. */
function WhyHere({ event }: { event: ThermalEvent }) {
  const reasons = event.reasons ?? [];
  if (!reasons.length && !event.facility) return null;
  const f = event.facility;
  return (
    <div>
      <span className="field-label">Why this point is here</span>
      {f && (
        <a
          href={f.url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-1.5 flex items-start gap-2 rounded-sm border border-border bg-muted/40 p-2 transition-colors hover:bg-muted"
        >
          <Factory className="mt-0.5 size-3.5 shrink-0 text-primary" />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[0.74rem] font-medium">
              {f.name || `Unnamed ${f.kind}`}
            </span>
            <span className="block text-[0.64rem] text-muted-foreground">
              {f.capacityMw ? `${Math.round(f.capacityMw).toLocaleString()} MW ` : ""}
              {f.kind} · {f.distanceKm.toFixed(1)} km away
              {f.operator ? ` · ${f.operator}` : ""}
            </span>
            <span className="mt-0.5 flex items-center gap-1 font-mono text-[0.6rem] text-primary">
              {f.source === "OpenStreetMap" ? `OSM ${f.ref}` : `WRI GPPD ${f.ref}`}
              <ExternalLink className="size-2.5" />
            </span>
          </span>
        </a>
      )}
      <ul className="mt-2 flex flex-col gap-1.5">
        {reasons.map((r) => (
          <li key={r} className="flex gap-2 text-[0.7rem] leading-snug text-foreground/85">
            <span className="mt-[0.42rem] size-1 shrink-0 rounded-full bg-muted-foreground" />
            <span>{r}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

const URGENCY_COLOR: Record<RecommendedAction["urgency"], string> = {
  Now: RISK_COLORS.CRITICAL,
  Today: RISK_COLORS.HIGH,
  "This week": RISK_COLORS.MODERATE,
  Monitor: "#71808f",
};

/** The score broken back into the three weighted components that produced it,
 *  plus the model's second opinion on the category. Nothing here is an
 *  after-the-fact attribution: the components sum to the score. */
function WhyRisky({ event }: { event: ThermalEvent }) {
  const factors = event.riskFactors ?? [];
  const model = event.model;
  if (!factors.length && !model) return null;
  return (
    <div>
      <span className="field-label">Why this is risky</span>
      {event.riskSummary && (
        <p className="mt-1 text-[0.78rem] leading-relaxed text-foreground/85">
          {event.riskSummary}
        </p>
      )}
      <div className="mt-2 flex flex-col gap-2.5">
        {factors.map((f) => (
          <div key={f.label}>
            <div className="flex items-baseline gap-2 text-[0.74rem]">
              <span className="text-foreground">{f.label}</span>
              <span className="font-mono tabular-nums text-muted-foreground">{f.value}</span>
              <span className="ml-auto font-mono tabular-nums text-muted-foreground">
                {f.points.toFixed(0)} pts
              </span>
            </div>
            <div className="mt-1 h-1.5 w-full rounded-full bg-muted">
              <div
                className="h-full rounded-full bg-primary"
                style={{ width: `${Math.max(2, f.share * 100)}%` }}
              />
            </div>
            <p className="mt-1 text-[0.68rem] leading-snug text-muted-foreground">{f.detail}</p>
          </div>
        ))}
      </div>
      {model && (
        <div className="mt-2.5 border-t border-border pt-2">
          <p className="text-[0.72rem] leading-snug text-foreground/85">
            <span className="font-medium">Model check.</span>{" "}
            {model.agrees
              ? `Agrees with the rule label at ${(model.confidence * 100).toFixed(0)}% confidence.`
              : `Would call this “${model.label}” instead at ${(model.confidence * 100).toFixed(0)}% confidence, so this one is worth a second look.`}
            {model.holdoutAgreement != null &&
              ` It reproduces the rules on ${(model.holdoutAgreement * 100).toFixed(0)}% of held-out events.`}
          </p>
          <p className="mt-1 text-[0.66rem] leading-snug text-muted-foreground">{model.caveat}</p>
        </div>
      )}
    </div>
  );
}

/** The response that follows from the category and the tier. Ordered, and
 *  deliberately conservative: nothing here says a fire is confirmed. */
function WhatToDo({ actions }: { actions: RecommendedAction[] }) {
  if (!actions.length) return null;
  return (
    <div>
      <span className="field-label">What to do</span>
      <ol className="mt-1 flex flex-col">
        {actions.map((a) => (
          <li
            key={a.step}
            className="grid grid-cols-[0.5rem_4.4rem_1fr] items-baseline gap-x-2 gap-y-1 border-b border-border py-1.5 last:border-b-0"
          >
            <span
              className="size-2 self-start rounded-[2px]"
              style={{ background: URGENCY_COLOR[a.urgency] }}
            />
            <span className="text-[0.68rem] text-muted-foreground">{a.urgency}</span>
            <span className="text-[0.76rem] text-foreground">{a.step}</span>
            <p className="col-start-3 text-[0.68rem] leading-snug text-muted-foreground">
              {a.detail}
            </p>
          </li>
        ))}
      </ol>
    </div>
  );
}

/** Earthquakes and open natural events close enough to change how the
 *  detection reads. A hotspot inside a live wildfire is not an industrial
 *  anomaly, and that belongs beside the risk, not on a separate page. */
function NearbyHazards({ event, hazards }: { event: ThermalEvent; hazards: Hazard[] }) {
  const near = hazardsNear(event.latitude, event.longitude, hazards, 150);
  if (!near.length) return null;
  return (
    <div>
      <span className="field-label">Hazards within 150 km</span>
      <div className="mt-1 flex flex-col">
        {near.map(({ hazard, km }) => (
          <div
            key={hazard.id}
            className="flex items-baseline gap-2 border-b border-border py-1 text-[0.72rem] last:border-b-0"
          >
            <span className="text-foreground">
              {hazard.kind === "earthquake" && hazard.magnitude != null
                ? `M${hazard.magnitude.toFixed(1)} earthquake`
                : hazard.categoryLabel}
            </span>
            <span className="truncate text-muted-foreground">{hazard.title}</span>
            <span className="ml-auto font-mono tabular-nums text-muted-foreground">
              {km.toFixed(0)} km
            </span>
          </div>
        ))}
      </div>
      <p className="mt-1 text-[0.66rem] leading-snug text-muted-foreground">
        Context only. Proximity is not causation, but a detection inside an active event reads
        differently from the same detection on a quiet day.
      </p>
    </div>
  );
}

export function EventDetail({
  event,
  sats = [],
  hazards = [],
}: {
  event: ThermalEvent | null;
  sats?: FireSat[];
  hazards?: Hazard[];
}) {
  if (!event) {
    return (
      <div className="panel flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
        <p className="text-sm font-semibold">No event selected</p>
        <p className="max-w-[22ch] text-sm text-muted-foreground">
          Click a thermal marker on the globe to open its investigation record.
        </p>
      </div>
    );
  }

  const risk = RISK_COLORS[event.riskLevel];
  return (
    <div className="panel flex h-full flex-col gap-4 overflow-y-auto p-4">
      <div>
        <div className="flex items-center justify-between">
          <span className="flex items-baseline gap-2">
            <span className="font-mono text-sm text-foreground">{event.id}</span>
            {event.priority != null && (
              <span className="font-mono text-[0.7rem] tabular-nums text-muted-foreground">
                #{event.priority} by risk
              </span>
            )}
          </span>
          <span className="flex items-center gap-1.5 rounded-sm border border-border bg-muted px-2 py-0.5 text-[0.68rem]">
            <span className="size-2 rounded-[2px]" style={{ background: risk }} />
            {event.status}
          </span>
        </div>
        <h2 className="mt-1 text-lg leading-tight font-semibold">{event.region}</h2>
        {event.district && (
          <p className="mt-0.5 text-[0.7rem] text-muted-foreground">{event.district} district</p>
        )}
        <span className="mt-2 inline-flex items-center gap-1.5 rounded-sm border border-border bg-muted px-2 py-0.5 text-[0.7rem]">
          <span
            className="size-2 rounded-[2px]"
            style={{ background: CATEGORY_COLORS[event.category] }}
          />
          {event.category}
        </span>
      </div>

      <WhyRisky event={event} />

      <WhatToDo actions={event.actions ?? []} />

      <WhyHere event={event} />

      <NearbyHazards event={event} hazards={hazards} />

      <div>
        <div className="flex items-end justify-between">
          <span className="field-label">Risk score</span>
          <span className="font-mono text-2xl tabular-nums">
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
        <span className="field-label">FRP trend (MW)</span>
        <Sparkline
          values={event.history.map((h) => h.frp)}
          color={CATEGORY_COLORS[event.category]}
        />
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

      <NextOverpasses lat={event.latitude} lon={event.longitude} sats={sats} />

      <p className="text-[0.68rem] leading-relaxed text-muted-foreground">
        Satellite detection is not ground truth. Risk and category are AI-assisted prioritization
        signals and require field verification before any operational response.
      </p>
    </div>
  );
}
