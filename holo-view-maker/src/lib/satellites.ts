import {
  degreesLat,
  degreesLong,
  eciToGeodetic,
  gstime,
  propagate,
  twoline2satrec,
  type SatRec,
} from "satellite.js";
import { sunElevation } from "@/lib/sun";

/** The polar orbiters whose VIIRS / MODIS scans produce NASA FIRMS hotspots. */
export interface FireSatDef {
  id: string;
  name: string;
  noradId: number;
  instrument: "VIIRS" | "MODIS";
  /** Full cross-track swath width. */
  swathKm: number;
  color: string;
  /** How this platform is labelled in pipeline event records. */
  firmsLabel: string;
}

export const FIRE_SATS: FireSatDef[] = [
  {
    id: "snpp",
    name: "Suomi NPP",
    noradId: 37849,
    instrument: "VIIRS",
    swathKm: 3060,
    color: "#67e8f9",
    firmsLabel: "VIIRS S-NPP",
  },
  {
    id: "n20",
    name: "NOAA-20",
    noradId: 43013,
    instrument: "VIIRS",
    swathKm: 3060,
    color: "#a78bfa",
    firmsLabel: "VIIRS NOAA-20",
  },
  {
    id: "n21",
    name: "NOAA-21",
    noradId: 54234,
    instrument: "VIIRS",
    swathKm: 3060,
    color: "#f0abfc",
    firmsLabel: "VIIRS NOAA-21",
  },
  {
    id: "aqua",
    name: "Aqua",
    noradId: 27424,
    instrument: "MODIS",
    swathKm: 2330,
    color: "#5eead4",
    firmsLabel: "MODIS Aqua",
  },
  {
    id: "terra",
    name: "Terra",
    noradId: 25994,
    instrument: "MODIS",
    swathKm: 2330,
    color: "#fde68a",
    firmsLabel: "MODIS Terra",
  },
];

export interface FireSat extends FireSatDef {
  satrec: SatRec;
  epoch: Date;
  periodMin: number;
}

export type TleSource = "live" | "cache" | "bundled";

export interface FireSatSet {
  sats: FireSat[];
  source: TleSource;
  /** When the orbital elements were obtained (ms). */
  fetchedAt: number;
}

const EARTH_RADIUS_KM = 6371;
const CACHE_KEY = "ti.fireSatTle.v1";
const RETRY_KEY = "ti.fireSatTle.retryAfter";
/** CelesTrak asks clients not to re-download the same element set more often
 * than every 2 h, and answers 403 to IPs that do — so cache generously and back
 * off after a failure instead of retrying on every page load. */
const CACHE_MAX_AGE_MS = 6 * 3600_000;
const RETRY_BACKOFF_MS = 2 * 3600_000;

function parseTle(text: string): Map<number, SatRec> {
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);
  const out = new Map<number, SatRec>();
  for (let i = 0; i < lines.length - 1; i++) {
    const l1 = lines[i] as string;
    const l2 = lines[i + 1] as string;
    if (!l1.startsWith("1 ") || !l2.startsWith("2 ")) continue;
    try {
      const rec = twoline2satrec(l1, l2);
      const id = Number(l1.slice(2, 7));
      const prev = out.get(id);
      // several element sets for one satellite: keep the freshest
      if (!prev || rec.jdsatepoch > prev.jdsatepoch) out.set(id, rec);
    } catch {
      /* malformed element set — skip it */
    }
    i += 1;
  }
  return out;
}

function buildSats(recs: Map<number, SatRec>): FireSat[] {
  return FIRE_SATS.flatMap((def) => {
    const satrec = recs.get(def.noradId);
    if (!satrec) return [];
    return [
      {
        ...def,
        satrec,
        epoch: new Date((satrec.jdsatepoch - 2440587.5) * 86400000),
        periodMin: (2 * Math.PI) / satrec.no,
      },
    ];
  });
}

function readCache(): { text: string; fetchedAt: number } | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    return raw ? (JSON.parse(raw) as { text: string; fetchedAt: number }) : null;
  } catch {
    return null;
  }
}

function writeCache(text: string) {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify({ text, fetchedAt: Date.now() }));
  } catch {
    /* storage unavailable (private mode) — we just refetch next load */
  }
}

function readRetryAfter(): number {
  try {
    return Number(localStorage.getItem(RETRY_KEY)) || 0;
  } catch {
    return 0;
  }
}

function writeRetryAfter(t: number) {
  try {
    localStorage.setItem(RETRY_KEY, String(t));
  } catch {
    /* storage unavailable */
  }
}

async function fetchCelestrak(): Promise<string> {
  const texts = await Promise.all(
    FIRE_SATS.map((s) =>
      fetch(`https://celestrak.org/NORAD/elements/gp.php?CATNR=${s.noradId}&FORMAT=TLE`, {
        signal: AbortSignal.timeout(12000),
      })
        .then((r) => (r.ok ? r.text() : ""))
        .catch(() => ""),
    ),
  );
  return texts.join("\n");
}

let inflight: Promise<FireSatSet> | null = null;

/**
 * Orbital elements for the FIRMS satellites. Fresh CelesTrak data when
 * reachable, a recent browser cache otherwise, and the snapshot shipped in
 * /data/fire-sats.tle as a last resort so the orbit layer never goes dark
 * mid-demo. Any satellite missing from a newer source is filled from an older
 * one rather than dropped. Concurrent callers (React dev mode mounts effects
 * twice) share one request.
 */
export function loadFireSats(): Promise<FireSatSet> {
  inflight ??= loadFireSatsOnce().finally(() => {
    inflight = null;
  });
  return inflight;
}

async function loadFireSatsOnce(): Promise<FireSatSet> {
  const cached = readCache();
  if (cached && Date.now() - cached.fetchedAt < CACHE_MAX_AGE_MS) {
    const sats = buildSats(parseTle(cached.text));
    if (sats.length === FIRE_SATS.length)
      return { sats, source: "cache", fetchedAt: cached.fetchedAt };
  }

  const backingOff = Date.now() < readRetryAfter();
  const [bundledText, liveText] = await Promise.all([
    fetch("/data/fire-sats.tle")
      .then((r) => (r.ok ? r.text() : ""))
      .catch(() => ""),
    backingOff ? Promise.resolve("") : fetchCelestrak(),
  ]);
  const live = parseTle(liveText);
  if (live.size > 0) writeCache(liveText);
  else if (!backingOff) writeRetryAfter(Date.now() + RETRY_BACKOFF_MS);

  const merged = parseTle([bundledText, cached?.text ?? "", liveText].join("\n"));
  const sats = buildSats(merged);
  if (live.size > 0) return { sats, source: "live", fetchedAt: Date.now() };
  if (cached) return { sats, source: "cache", fetchedAt: cached.fetchedAt };
  const newestEpoch = Math.max(0, ...sats.map((s) => s.epoch.getTime()));
  return { sats, source: "bundled", fetchedAt: newestEpoch };
}

export interface SubPoint {
  lat: number;
  lon: number;
  altKm: number;
}

/** Sub-satellite point (geodetic) and altitude at a given instant. */
export function subPoint(satrec: SatRec, date: Date): SubPoint | null {
  const pv = propagate(satrec, date);
  // SGP4 reports a failed propagation (e.g. a decayed orbit) as `position: false`
  if (!pv?.position || typeof pv.position !== "object") return null;
  const geo = eciToGeodetic(pv.position, gstime(date));
  return { lat: degreesLat(geo.latitude), lon: degreesLong(geo.longitude), altKm: geo.height };
}

export function greatCircleKm(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const r = Math.PI / 180;
  const dLat = (lat2 - lat1) * r;
  const dLon = (lon2 - lon1) * r;
  const a =
    Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.min(1, Math.sqrt(a)));
}

/** Angular radius (radians) of a sensor's swath, as seen from Earth's centre. */
export function swathHalfAngle(sat: FireSatDef): number {
  return sat.swathKm / 2 / EARTH_RADIUS_KM;
}

export interface Pass {
  sat: FireSat;
  /** Closest approach of the ground track to the target. */
  time: Date;
  /** Ground distance from nadir at closest approach — larger means coarser edge-of-scan pixels. */
  offNadirKm: number;
  daylight: boolean;
}

/**
 * Upcoming overpasses in which the target falls inside each sensor's swath.
 * Steps the orbit minute by minute and reports the closest approach of every
 * contiguous in-swath interval. A satellite over the target right now reports
 * a pass at (about) the current time.
 */
export function nextPasses(
  sats: FireSat[],
  lat: number,
  lon: number,
  from: Date = new Date(),
  hours = 36,
  stepSec = 60,
): Pass[] {
  const out: Pass[] = [];
  const start = from.getTime();
  const end = start + hours * 3600_000;
  for (const sat of sats) {
    const half = sat.swathKm / 2;
    let best: { t: number; d: number } | null = null;
    const flush = () => {
      if (!best) return;
      const time = new Date(best.t);
      out.push({ sat, time, offNadirKm: best.d, daylight: sunElevation(lat, lon, time) > 0 });
      best = null;
    };
    for (let t = start; t <= end; t += stepSec * 1000) {
      const p = subPoint(sat.satrec, new Date(t));
      if (!p) continue;
      const d = greatCircleKm(lat, lon, p.lat, p.lon);
      if (d <= half) {
        if (!best || d < best.d) best = { t, d };
      } else {
        flush();
      }
    }
    flush();
  }
  return out.sort((a, b) => a.time.getTime() - b.time.getTime());
}

/** Default overpass target: the Jharia coalfield, centre of the monitored belt. */
export const DEFAULT_AOI = { name: "Jharia coalfield", lat: 23.75, lon: 86.42 };
