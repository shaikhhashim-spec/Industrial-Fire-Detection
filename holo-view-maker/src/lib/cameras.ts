/*
 * India CCTV layer: the public-space cameras OpenStreetMap volunteers have
 * mapped (scripts/build_india_cameras.py writes /data/cameras.geojson). It is
 * locations and tags only. No camera is contacted and there is no video, so
 * every label here says "mapped", never "live".
 */
import type { Feature, FeatureCollection, Point, Polygon } from "geojson";
import type { ExpressionSpecification } from "maplibre-gl";
import { assetUrl } from "@/lib/asset-url";
import { distanceKm } from "@/lib/hazards";

export const CAMERA_KINDS = [
  "Traffic",
  "Streets and public spaces",
  "Buildings",
  "Open areas",
  "Unspecified",
] as const;
export type CameraKind = (typeof CAMERA_KINDS)[number];

/** Quiet, desaturated hues: a context layer must not compete with risk colours
 * or with the one accent, which marks selection. */
export const CAMERA_COLORS: Record<CameraKind, string> = {
  Traffic: "#9db4d1",
  "Streets and public spaces": "#c8b88a",
  Buildings: "#a99bc7",
  "Open areas": "#8fbf9f",
  Unspecified: "#71808f",
};

export interface Camera {
  /** OpenStreetMap node id. */
  id: number;
  lat: number;
  lon: number;
  kind: CameraKind;
  type?: string;
  mount?: string;
  /** Degrees clockwise from north, only when a mapper recorded it. */
  heading?: number;
  /** Field of view in degrees, only when a mapper recorded it. */
  angle?: number;
  plateReader?: boolean;
  operator?: string;
  name?: string;
  state: string;
}

export interface CameraMeta {
  source: string;
  license: string;
  osmTimestamp?: string;
  generatedAt: string;
  count: number;
  withHeading: number;
  kinds: Record<string, number>;
}

export interface CameraData {
  cameras: Camera[];
  collection: FeatureCollection<Point>;
  meta: CameraMeta;
}

export async function fetchCameras(): Promise<CameraData | null> {
  try {
    const res = await fetch(assetUrl("data/cameras.geojson"));
    if (!res.ok) return null;
    const fc = (await res.json()) as FeatureCollection<Point> & { meta?: CameraMeta };
    if (!Array.isArray(fc.features) || !fc.meta) return null;
    const cameras: Camera[] = fc.features.map((f) => ({
      ...(f.properties as Omit<Camera, "lat" | "lon">),
      lon: f.geometry.coordinates[0]!,
      lat: f.geometry.coordinates[1]!,
    }));
    return { cameras, collection: fc, meta: fc.meta };
  } catch (err) {
    console.warn("Could not read /data/cameras.geojson:", err);
    return null;
  }
}

/** Colour by what the camera watches. Cast through unknown: the entries are
 * built from the table above, which the literal expression type can't follow. */
export const CAMERA_COLOR_EXPR = [
  "match",
  ["get", "kind"],
  ...Object.entries(CAMERA_COLORS).flat(),
  "#71808f",
] as unknown as ExpressionSpecification;

const COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];

export function compass(deg: number): string {
  return COMPASS[Math.round((((deg % 360) + 360) % 360) / 45) % 8]!;
}

export function describeCamera(c: Camera): string {
  const bits = [c.type, c.mount ? `${c.mount.replace("_", " ")} mount` : undefined].filter(Boolean);
  return bits.length ? bits.join(", ") : "type not mapped";
}

/** The nearest cameras to a point, closest first, within maxKm. */
export function nearestCameras(
  lat: number,
  lon: number,
  cameras: Camera[],
  limit: number,
  maxKm: number,
): { camera: Camera; km: number }[] {
  // A degree of latitude is ~111 km, so this cheap box rejects almost everything
  // before the trigonometry runs.
  const dLat = maxKm / 111;
  const dLon = maxKm / (111 * Math.max(0.2, Math.cos((lat * Math.PI) / 180)));
  const out: { camera: Camera; km: number }[] = [];
  for (const camera of cameras) {
    if (Math.abs(camera.lat - lat) > dLat || Math.abs(camera.lon - lon) > dLon) continue;
    const km = distanceKm(lat, lon, camera.lat, camera.lon);
    if (km <= maxKm) out.push({ camera, km });
  }
  return out.sort((a, b) => a.km - b.km).slice(0, limit);
}

export function countWithin(lat: number, lon: number, cameras: Camera[], maxKm: number): number {
  return nearestCameras(lat, lon, cameras, Number.MAX_SAFE_INTEGER, maxKm).length;
}

/** Wedge radius in metres. The bearing is mapped; the reach and the default 60
 * degree view are typical values for drawing, not a measured coverage. */
const WEDGE_RADIUS_M = 45;
const DEFAULT_FOV = 60;

function offset(lat: number, lon: number, bearingDeg: number, metres: number): [number, number] {
  const b = (bearingDeg * Math.PI) / 180;
  const dLat = (metres * Math.cos(b)) / 111_320;
  const dLon = (metres * Math.sin(b)) / (111_320 * Math.cos((lat * Math.PI) / 180));
  return [lon + dLon, lat + dLat];
}

/** A small view wedge for every camera that has a mapped heading. */
export function cameraWedges(cameras: Camera[]): FeatureCollection<Polygon> {
  const features: Feature<Polygon>[] = [];
  for (const c of cameras) {
    if (c.heading == null) continue;
    const fov = c.angle && c.angle < 180 ? c.angle : DEFAULT_FOV;
    const steps = 6;
    const ring: [number, number][] = [[c.lon, c.lat]];
    for (let i = 0; i <= steps; i++) {
      ring.push(offset(c.lat, c.lon, c.heading - fov / 2 + (fov * i) / steps, WEDGE_RADIUS_M));
    }
    ring.push([c.lon, c.lat]);
    features.push({
      type: "Feature",
      geometry: { type: "Polygon", coordinates: [ring] },
      properties: { id: c.id, color: CAMERA_COLORS[c.kind] },
    });
  }
  return { type: "FeatureCollection", features };
}

/** The map icon for one kind. A camera with a mapped heading is a dot with a
 * pointer that rotates to face it; one without is a dot with a lens ring. */
export function cameraIconName(kind: string, directional: boolean): string {
  return `cam-${kind}-${directional ? "dir" : "dot"}`;
}

export function drawCameraIcon(color: string, directional: boolean): ImageData {
  const size = 48;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  const c = size / 2;
  ctx.lineJoin = "round";
  ctx.strokeStyle = "#05080c";
  ctx.lineWidth = 2.5;
  ctx.fillStyle = color;
  if (directional) {
    ctx.beginPath();
    ctx.moveTo(c, 3);
    ctx.lineTo(c + 8, c - 3);
    ctx.lineTo(c - 8, c - 3);
    ctx.closePath();
    ctx.stroke();
    ctx.fill();
  }
  ctx.beginPath();
  ctx.arc(c, c, 8.5, 0, Math.PI * 2);
  ctx.stroke();
  ctx.fill();
  ctx.fillStyle = "#05080c";
  ctx.beginPath();
  ctx.arc(c, c, 3.2, 0, Math.PI * 2);
  ctx.fill();
  return ctx.getImageData(0, 0, size, size);
}
