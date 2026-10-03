import { assetUrl } from "@/lib/asset-url";

export type Category =
  | "Likely Industrial Fire"
  | "Persistent Non-Industrial Thermal Source"
  | "Transient Industrial Flare"
  | "Likely Agricultural Burning"
  | "Sun Glint / False Positive"
  | "Likely Wildfire"
  | "Persistent Industrial Activity"
  | "Requires Verification";

export type RiskLevel = "LOW" | "MODERATE" | "HIGH" | "CRITICAL";

export const CATEGORY_COLORS: Record<Category, string> = {
  "Likely Industrial Fire": "#3987e5",
  "Persistent Non-Industrial Thermal Source": "#d95926",
  "Transient Industrial Flare": "#199e70",
  "Likely Agricultural Burning": "#c98500",
  "Sun Glint / False Positive": "#d55181",
  "Likely Wildfire": "#008300",
  "Persistent Industrial Activity": "#9085e9",
  "Requires Verification": "#e66767",
};

/** Risk is a state, so it wears the reserved status palette (good / warning /
 *  serious / critical) and is always shown with its label. */
export const RISK_COLORS: Record<RiskLevel, string> = {
  LOW: "#0ca30c",
  MODERATE: "#fab219",
  HIGH: "#ec835a",
  CRITICAL: "#d03b3b",
};

/** Nearest known heat-producing facility credited for a detection (open data). */
export interface Facility {
  name: string;
  kind: string;
  detail: string;
  operator: string;
  capacityMw: number | null;
  distanceKm: number;
  source: string;
  ref: string;
  url: string;
}

/** Satellite evidence behind an event, over the pipeline's history window. */
export interface Evidence {
  detections: number;
  days: number;
  firstSeen: string | null;
  lastSeen: string | null;
  maxFrp: number;
  meanFrp: number;
  nightPasses: number;
  lowConfidenceShare: number;
  meanConfidence: number | null;
  satellites: string[];
}

/** One weighted component of the risk score. The three components add up to
 *  the score exactly, so this is arithmetic rather than attribution. */
export interface RiskFactor {
  label: string;
  points: number;
  share: number;
  value: string;
  detail: string;
}

/** The random forest's second opinion on the rule label. */
export interface ModelCheck {
  label: string;
  confidence: number;
  agrees: boolean;
  holdoutAgreement?: number | null;
  caveat: string;
}

export interface RecommendedAction {
  step: string;
  detail: string;
  urgency: "Now" | "Today" | "This week" | "Monitor";
}

/** Downwind smoke/gas dispersion cone from live wind at the event's location —
 *  a visual heuristic (cone length scales with wind speed and FRP), not a
 *  scientific atmospheric dispersion model. Only high-intensity events carry one. */
export interface PlumeData {
  windSpeedKmh: number;
  windDirectionDeg: number;
  downwindBearingDeg: number;
  coneLengthKm: number;
  /** [lon, lat] pairs, apex-first — GeoJSON coordinate order. */
  polygon: [number, number][];
  source?: string;
  observedAt?: string | null;
  estimated?: boolean;
}

/** A screening heuristic, not the Canadian Fire Weather Index or a forecast. */
export interface SpreadPotential {
  score: number;
  label: string;
  factors?: Record<string, number>;
  caveat?: string;
}

export interface ThermalEvent {
  id: string;
  region: string;
  latitude: number;
  longitude: number;
  category: Category;
  riskScore: number;
  riskLevel: RiskLevel;
  frp: number;
  brightness: number | null;
  confidence: number;
  persistenceDays: number;
  detectionCount: number;
  satellite: "VIIRS S-NPP" | "VIIRS NOAA-20" | "VIIRS NOAA-21" | "MODIS Aqua" | "MODIS Terra";
  daynight: "D" | "N";
  status: "NEW" | "RECURRING" | "PERSISTENT" | "HIGH RISK" | "CRITICAL";
  acqDate: string;
  history: { date: string; frp: number; confidence: number }[];
  // open-source context (national pipeline) — absent on older exports
  state?: string;
  district?: string | null;
  place?: { name: string; distanceKm: number; direction: string } | null;
  satellites?: string[];
  facility?: Facility | null;
  /** Backed by more than one pixel on one pass (repeat, 2+ days, or a mapped facility). */
  corroborated?: boolean;
  reasons?: string[];
  evidence?: Evidence | null;
  /** Rank by risk across the whole run, 1 being the highest. */
  priority?: number | null;
  riskSummary?: string | null;
  riskFactors?: RiskFactor[];
  actions?: RecommendedAction[];
  model?: ModelCheck | null;
  plume?: PlumeData;
  country?: string | null;
  spreadPotential?: SpreadPotential | null;
}

/** Provenance written by the Python exporter alongside the events. */
export interface DataMeta {
  source: "firms_live" | "local_cache" | "mixed" | "none";
  generatedAt: string;
  events: number;
  windowDays: number;
  attribution: string[];
  scope?: string;
  coverage?: string;
  partial?: boolean;
  feeds?: (string | { source: string; status: string; observations: number })[];
  weatherEnrichedEvents?: number;
  datasets?: { scope: string; generatedAt: string; events: number; source: string }[];
}

/** "none" means the pipeline has not exported anything the globe can draw. */
export type DataSource = "live" | "none";

export const CATEGORIES = Object.keys(CATEGORY_COLORS) as Category[];

/**
 * Loads the thermal detections the Python pipeline exported to
 * `/data/events.json` and the optional worldwide feed. Live data only: when a file is missing or not
 * marked as a real FIRMS run, the globe shows an empty state rather than
 * standing in something made up.
 */
export async function fetchThermalEvents(): Promise<{
  events: ThermalEvent[];
  source: DataSource;
  meta: DataMeta | null;
}> {
  const read = async (
    filename: string,
    scope: string,
  ): Promise<{
    events: ThermalEvent[];
    source: DataSource;
    meta: DataMeta | null;
  }> => {
    try {
      const res = await fetch(assetUrl(`data/${filename}`), { cache: "no-cache" });
      if (res.ok) {
        const data = await res.json();
        const list: ThermalEvent[] = Array.isArray(data) ? data : (data?.events ?? []);
        const meta: DataMeta | null = Array.isArray(data) ? null : (data?.meta ?? null);
        const live = meta ? ["firms_live", "local_cache", "mixed"].includes(meta.source) : false;
        if (live && Array.isArray(list)) {
          const valid = list.filter(
            (e) =>
              e &&
              typeof e.id === "string" &&
              Number.isFinite(e.latitude) &&
              Math.abs(e.latitude) <= 90 &&
              Number.isFinite(e.longitude) &&
              Math.abs(e.longitude) <= 180 &&
              Number.isFinite(e.riskScore) &&
              Number.isFinite(e.frp) &&
              CATEGORIES.includes(e.category) &&
              e.riskLevel in RISK_COLORS,
          );
          return {
            events: valid.sort((a, b) => b.riskScore - a.riskScore),
            source: "live",
            meta: meta ? { ...meta, scope: meta.scope ?? scope } : null,
          };
        }
      }
    } catch (err) {
      console.warn(`Could not read /data/${filename}:`, err);
    }
    return { events: [], source: "none", meta: null };
  };
  const [national, global] = await Promise.all([
    read("events.json", "india"),
    read("global-events.json", "global"),
  ]);
  if (!global.meta) return national;
  // Match the existing 0.01-degree cell before adding global observations;
  // the national dossier supplies the deeper history and facility evidence.
  const cell = (e: ThermalEvent) =>
    `${Math.floor(e.longitude * 100)}:${Math.floor(e.latitude * 100)}`;
  const globalDates = new Map<string, string>();
  for (const e of global.events) {
    const key = cell(e);
    if ((globalDates.get(key) ?? "") < e.acqDate) globalDates.set(key, e.acqDate);
  }
  const nationalEvents = national.events.filter(
    (e) => (globalDates.get(cell(e)) ?? "") <= e.acqDate,
  );
  const nationalCells = new Set(nationalEvents.map(cell));
  const events = [...nationalEvents, ...global.events.filter((e) => !nationalCells.has(cell(e)))];
  events.sort((a, b) => b.riskScore - a.riskScore);
  const datasets = [national.meta, global.meta].filter((m): m is DataMeta => m !== null);
  return {
    events,
    source: "live",
    meta: {
      ...global.meta,
      events: events.length,
      partial: global.meta.partial || datasets.some((m) => m.partial),
      attribution: [...new Set(datasets.flatMap((m) => m.attribution ?? []))],
      datasets: datasets.map((m) => ({
        scope: m.scope ?? "india",
        generatedAt: m.generatedAt,
        events: m.events,
        source: m.source,
      })),
    },
  };
}
