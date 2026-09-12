/*
 * Hazard context: recent earthquakes (USGS) and open natural events (NASA
 * EONET). Both are keyless public feeds.
 *
 * They earn their place on a thermal globe because they change how a detection
 * reads. A hotspot inside an active EONET wildfire perimeter is not an
 * industrial anomaly, and a cluster of new heat hours after a significant
 * earthquake near a refinery is worth looking at differently from the same
 * cluster on a quiet day. The layers are context for the thermal data, not
 * decoration.
 */

export type HazardKind = "earthquake" | "eonet";

export interface Hazard {
  id: string;
  kind: HazardKind;
  title: string;
  lat: number;
  lon: number;
  /** Epoch milliseconds. */
  time: number;
  url: string;
  /** Earthquakes only. */
  magnitude?: number | undefined;
  depthKm?: number | undefined;
  /** EONET only: the category id and its display label. */
  category: string;
  categoryLabel: string;
  /** EONET storm-style events carry a track of [lat, lon] points. */
  track?: [number, number][] | undefined;
}

/** M2.5+ in the past week: small enough to stay current, big enough to matter. */
const USGS_FEED = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_week.geojson";
const EONET_FEED = "https://eonet.gsfc.nasa.gov/api/v3/events?status=open&limit=250";

const FETCH_TIMEOUT_MS = 12_000;

/** Age is the thing an analyst reads first, so it gets the colour. */
export const QUAKE_COLOR = {
  recent: "#e5484d",
  day3: "#e07a3c",
  older: "#8b95a1",
} as const;

export function quakeColor(time: number, now = Date.now()): string {
  const ageH = (now - time) / 3_600_000;
  if (ageH <= 24) return QUAKE_COLOR.recent;
  if (ageH <= 72) return QUAKE_COLOR.day3;
  return QUAKE_COLOR.older;
}

/** EONET category ids to the validated categorical palette, in fixed order. */
export const EONET_COLORS: Record<string, string> = {
  wildfires: "#d95926",
  severeStorms: "#3987e5",
  volcanoes: "#d55181",
  floods: "#199e70",
  drought: "#c98500",
  dustHaze: "#9085e9",
  seaLakeIce: "#5cb8dc",
  snow: "#a1adba",
  earthquakes: "#e66767",
  landslides: "#8b5a2b",
  manmade: "#71808f",
  waterColor: "#008300",
  tempExtremes: "#e07a3c",
};

async function getJson(url: string): Promise<unknown> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const res = await fetch(url, { signal: controller.signal });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } finally {
    clearTimeout(timer);
  }
}

interface QuakeFeature {
  id?: string;
  properties?: { mag?: number; place?: string; time?: number; url?: string };
  geometry?: { coordinates?: number[] };
}

export async function fetchEarthquakes(): Promise<Hazard[]> {
  const data = (await getJson(USGS_FEED)) as { features?: QuakeFeature[] };
  const features = data.features ?? [];
  return features.flatMap((f): Hazard[] => {
    const coords = f.geometry?.coordinates ?? [];
    const lon = coords[0];
    const lat = coords[1];
    const depth = coords[2];
    if (typeof lon !== "number" || typeof lat !== "number") return [];
    return [
      {
        id: String(f.id ?? `${lon},${lat},${f.properties?.time}`),
        kind: "earthquake",
        title: f.properties?.place ?? "Earthquake",
        lat,
        lon,
        time: Number(f.properties?.time ?? Date.now()),
        url: f.properties?.url ?? "",
        magnitude: typeof f.properties?.mag === "number" ? f.properties.mag : undefined,
        depthKm: typeof depth === "number" ? depth : undefined,
        category: "earthquakes",
        categoryLabel: "Earthquake",
      },
    ];
  });
}

interface EonetGeometry {
  date?: string;
  type?: string;
  coordinates?: unknown;
}

interface EonetEvent {
  id?: string;
  title?: string;
  link?: string;
  sources?: { url?: string }[];
  categories?: { id?: string; title?: string }[];
  geometry?: EonetGeometry[];
}

/** EONET points are [lon, lat]; polygons nest one level deeper. */
function lastPoint(g: EonetGeometry): [number, number] | null {
  const c = g.coordinates;
  if (Array.isArray(c) && typeof c[0] === "number" && typeof c[1] === "number") {
    return [c[0], c[1]];
  }
  if (Array.isArray(c) && Array.isArray(c[0])) {
    const flat = (c as unknown[]).flat(Infinity) as number[];
    const [lon, lat] = flat;
    if (typeof lon === "number" && typeof lat === "number") return [lon, lat];
  }
  return null;
}

export async function fetchEonet(): Promise<Hazard[]> {
  const data = (await getJson(EONET_FEED)) as { events?: EonetEvent[] };
  const events = data.events ?? [];
  return events.flatMap((e): Hazard[] => {
    const geoms = e.geometry ?? [];
    if (!geoms.length) return [];
    const latest = geoms[geoms.length - 1];
    const point = latest ? lastPoint(latest) : null;
    if (!latest || !point) return [];
    const [lon, lat] = point;

    // A storm's earlier positions make its path, which is the useful part.
    const track = geoms
      .map(lastPoint)
      .filter((p): p is [number, number] => p !== null)
      .map(([plon, plat]) => [plat, plon] as [number, number]);

    const category = e.categories?.[0];
    return [
      {
        id: String(e.id ?? `${lon},${lat}`),
        kind: "eonet",
        title: e.title ?? "Natural event",
        lat,
        lon,
        time: latest.date ? Date.parse(latest.date) : Date.now(),
        url: e.sources?.[0]?.url ?? e.link ?? "",
        category: category?.id ?? "manmade",
        categoryLabel: category?.title ?? "Natural event",
        track: track.length > 1 ? track : undefined,
      },
    ];
  });
}

const EARTH_KM = 6371.0088;

/** Great-circle distance, for tying a hazard to a thermal detection. */
export function distanceKm(aLat: number, aLon: number, bLat: number, bLon: number): number {
  const toRad = Math.PI / 180;
  const dLat = (bLat - aLat) * toRad;
  const dLon = (bLon - aLon) * toRad;
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(aLat * toRad) * Math.cos(bLat * toRad) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_KM * Math.asin(Math.min(1, Math.sqrt(h)));
}

/** Hazards close enough to a hotspot to change how it reads. */
export function hazardsNear(
  lat: number,
  lon: number,
  hazards: Hazard[],
  radiusKm: number,
): { hazard: Hazard; km: number }[] {
  return hazards
    .map((hazard) => ({ hazard, km: distanceKm(lat, lon, hazard.lat, hazard.lon) }))
    .filter((h) => h.km <= radiusKm)
    .sort((a, b) => a.km - b.km)
    .slice(0, 3);
}
