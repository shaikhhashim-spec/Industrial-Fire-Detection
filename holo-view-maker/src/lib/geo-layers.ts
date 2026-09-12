/**
 * Pure GeoJSON builders for the MapLibre globe. Everything the map draws goes
 * through here as plain data, so each layer is a single GPU draw rather than
 * one scene object per event.
 */
import type {
  Feature,
  FeatureCollection,
  LineString,
  MultiLineString,
  Point,
  Polygon,
} from "geojson";
import { CATEGORY_COLORS, RISK_COLORS, type ThermalEvent } from "@/lib/thermal";
import { subPoint, swathHalfAngle, type FireSat } from "@/lib/satellites";
import { EONET_COLORS, quakeColor, type Hazard } from "@/lib/hazards";

const DEG = Math.PI / 180;

export const EMPTY_FC: FeatureCollection = { type: "FeatureCollection", features: [] };

export function eventsToGeoJSON(events: ThermalEvent[]): FeatureCollection<Point> {
  return {
    type: "FeatureCollection",
    features: events.map((e) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [e.longitude, e.latitude] },
      properties: {
        id: e.id,
        region: e.region,
        risk: e.riskScore,
        level: e.riskLevel,
        frp: e.frp,
        category: e.category,
        catColor: CATEGORY_COLORS[e.category],
        riskColor: RISK_COLORS[e.riskLevel],
      },
    })),
  };
}

/** Split a lon/lat path wherever it jumps across the antimeridian, ending and
 * restarting each piece exactly on ±180° so nothing streaks across the map. */
export function splitAntimeridian(points: [number, number][]): [number, number][][] {
  const parts: [number, number][][] = [];
  let current: [number, number][] = [];
  for (let i = 0; i < points.length; i++) {
    const p = points[i]!;
    const prev = points[i - 1];
    if (prev && Math.abs(p[0] - prev[0]) > 180) {
      const east = prev[0] > 0; // crossing eastward past +180
      const lonA = prev[0];
      const lonB = east ? p[0] + 360 : p[0] - 360;
      const edge = east ? 180 : -180;
      const t = (edge - lonA) / (lonB - lonA);
      const lat = prev[1] + t * (p[1] - prev[1]);
      current.push([edge, lat]);
      parts.push(current);
      current = [[-edge, lat]];
    }
    current.push(p);
  }
  if (current.length > 1) parts.push(current);
  return parts;
}

/** Destination point at angular distance `d` (radians) and bearing `brg` (radians). */
function destination(lat: number, lon: number, d: number, brg: number): [number, number] {
  const φ1 = lat * DEG;
  const λ1 = lon * DEG;
  const φ2 = Math.asin(Math.sin(φ1) * Math.cos(d) + Math.cos(φ1) * Math.sin(d) * Math.cos(brg));
  const λ2 =
    λ1 +
    Math.atan2(
      Math.sin(brg) * Math.sin(d) * Math.cos(φ1),
      Math.cos(d) - Math.sin(φ1) * Math.sin(φ2),
    );
  return [((((λ2 / DEG + 540) % 360) + 360) % 360) - 180, φ2 / DEG];
}

export interface SatLive {
  sat: FireSat;
  lat: number;
  lon: number;
  altKm: number;
}

export function satPositions(sats: FireSat[], now: Date): SatLive[] {
  return sats.flatMap((sat) => {
    const p = subPoint(sat.satrec, now);
    return p ? [{ sat, lat: p.lat, lon: p.lon, altKm: p.altKm }] : [];
  });
}

export function satPointsGeoJSON(live: SatLive[]): FeatureCollection<Point> {
  return {
    type: "FeatureCollection",
    features: live.map((s) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [s.lon, s.lat] },
      properties: { id: s.sat.id, color: s.sat.color },
    })),
  };
}

/** Ground track of one orbit centred on `now`: the half behind and the half ahead. */
export function satTracksGeoJSON(
  sats: FireSat[],
  now: Date,
  stepSec = 30,
): FeatureCollection<MultiLineString> {
  const features: Feature<MultiLineString>[] = [];
  for (const sat of sats) {
    const half = Math.round((sat.periodMin * 60) / 2 / stepSec);
    const past: [number, number][] = [];
    const ahead: [number, number][] = [];
    for (let i = -half; i <= half; i++) {
      const p = subPoint(sat.satrec, new Date(now.getTime() + i * stepSec * 1000));
      if (!p) continue;
      if (i <= 0) past.push([p.lon, p.lat]);
      if (i >= 0) ahead.push([p.lon, p.lat]);
    }
    features.push(
      {
        type: "Feature",
        geometry: { type: "MultiLineString", coordinates: splitAntimeridian(past) },
        properties: { id: sat.id, color: sat.color, part: "past" },
      },
      {
        type: "Feature",
        geometry: { type: "MultiLineString", coordinates: splitAntimeridian(ahead) },
        properties: { id: sat.id, color: sat.color, part: "ahead" },
      },
    );
  }
  return { type: "FeatureCollection", features };
}

/**
 * Swath footprint of each sensor right now: the ground circle it can image.
 * The outline is always drawn; the translucent fill only when the circle
 * neither wraps a pole nor crosses the antimeridian (a lon/lat polygon can't
 * represent those, and polar orbiters do both every half orbit).
 */
export function swathGeoJSON(live: SatLive[]): {
  fill: FeatureCollection<Polygon>;
  outline: FeatureCollection<MultiLineString>;
} {
  const fill: Feature<Polygon>[] = [];
  const outline: Feature<MultiLineString>[] = [];
  for (const s of live) {
    const r = swathHalfAngle(s.sat);
    const ring: [number, number][] = [];
    for (let i = 0; i <= 72; i++) ring.push(destination(s.lat, s.lon, r, (i / 72) * 2 * Math.PI));
    const parts = splitAntimeridian(ring);
    const props = { id: s.sat.id, color: s.sat.color };
    outline.push({
      type: "Feature",
      geometry: { type: "MultiLineString", coordinates: parts },
      properties: props,
    });
    const wrapsPole = Math.abs(s.lat) + r / DEG >= 90;
    if (parts.length === 1 && !wrapsPole) {
      fill.push({
        type: "Feature",
        geometry: { type: "Polygon", coordinates: [ring] },
        properties: props,
      });
    }
  }
  return {
    fill: { type: "FeatureCollection", features: fill },
    outline: { type: "FeatureCollection", features: outline },
  };
}

export function graticuleGeoJSON(step = 30): FeatureCollection<LineString> {
  const features: Feature<LineString>[] = [];
  for (let lat = -60; lat <= 60; lat += step) {
    const coords: [number, number][] = [];
    for (let lon = -180; lon <= 180; lon += 2) coords.push([lon, lat]);
    features.push({
      type: "Feature",
      geometry: { type: "LineString", coordinates: coords },
      properties: {},
    });
  }
  for (let lon = -180; lon < 180; lon += step) {
    const coords: [number, number][] = [];
    for (let lat = -84; lat <= 84; lat += 2) coords.push([lon, lat]);
    features.push({
      type: "Feature",
      geometry: { type: "LineString", coordinates: coords },
      properties: {},
    });
  }
  return { type: "FeatureCollection", features };
}

// ── hazard context: earthquakes and open natural events ──

export function hazardsGeoJSON(items: Hazard[], now = Date.now()): FeatureCollection<Point> {
  return {
    type: "FeatureCollection",
    features: items.map((h) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [h.lon, h.lat] },
      properties: {
        id: h.id,
        mag: h.magnitude ?? 0,
        recent: now - h.time < 86400000,
        color:
          h.kind === "earthquake"
            ? quakeColor(h.time, now)
            : (EONET_COLORS[h.category] ?? "#a1adba"),
      },
    })),
  };
}

/** The path a storm has taken so far, split at the antimeridian. */
export function stormTracksGeoJSON(items: Hazard[]): FeatureCollection<MultiLineString> {
  return {
    type: "FeatureCollection",
    features: items
      .filter((h) => h.track && h.track.length > 1)
      .map((h) => ({
        type: "Feature",
        geometry: {
          type: "MultiLineString",
          coordinates: splitAntimeridian(
            h.track!.map(([lat, lon]) => [lon, lat] as [number, number]),
          ),
        },
        properties: { color: EONET_COLORS[h.category] ?? "#a1adba" },
      })),
  };
}
