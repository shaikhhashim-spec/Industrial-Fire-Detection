/*
 * India live webcams listed on SkylineWebcams (scripts/build_india_webcams.py
 * writes /data/webcams.geojson). Link-out only: the site does not allow its
 * pages to be embedded, so this holds a name, a town and a URL, never a stream.
 * The position is the town centre, not the camera.
 */
import type { FeatureCollection, Point } from "geojson";
import { assetUrl } from "@/lib/asset-url";

export interface Webcam {
  id: string;
  name: string;
  about: string;
  town: string;
  state: string;
  url: string;
  positionFrom: string;
  lat: number;
  lon: number;
}

export interface WebcamData {
  webcams: Webcam[];
  collection: FeatureCollection<Point>;
}

export async function fetchWebcams(): Promise<WebcamData | null> {
  try {
    const res = await fetch(assetUrl("data/webcams.geojson"));
    if (!res.ok) return null;
    const fc = (await res.json()) as FeatureCollection<Point>;
    if (!Array.isArray(fc.features)) return null;
    const webcams: Webcam[] = fc.features.map((f) => ({
      ...(f.properties as Omit<Webcam, "lat" | "lon">),
      lon: f.geometry.coordinates[0]!,
      lat: f.geometry.coordinates[1]!,
    }));
    return { webcams, collection: fc };
  } catch (err) {
    console.warn("Could not read /data/webcams.geojson:", err);
    return null;
  }
}
