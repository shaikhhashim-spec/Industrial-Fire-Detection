import { useEffect, useState } from "react";
import * as THREE from "three";
import { latLonToVec3 } from "@/lib/thermal";

type Ring = number[][];

function ringsFromFeature(geom: { type: string; coordinates: unknown }): Ring[] {
  if (geom.type === "Polygon") return geom.coordinates as Ring[];
  if (geom.type === "MultiPolygon") return (geom.coordinates as Ring[][]).flat();
  return [];
}

export function Coastlines({ radius = 2.01 }: { radius?: number }) {
  const [geometry, setGeometry] = useState<THREE.BufferGeometry | null>(null);

  useEffect(() => {
    let alive = true;
    const baseUrl = import.meta.env.BASE_URL;
    fetch(`${baseUrl}geo/land-110m.geojson`)
      .then((r) => r.json())
      .then((data: { features: { geometry: { type: string; coordinates: unknown } }[] }) => {
        if (!alive) return;
        const positions: number[] = [];
        for (const f of data.features) {
          for (const ring of ringsFromFeature(f.geometry)) {
            for (let i = 0; i < ring.length - 1; i++) {
              const a = ring[i] as number[];
              const b = ring[i + 1] as number[];
              positions.push(...latLonToVec3(a[1] as number, a[0] as number, radius));
              positions.push(...latLonToVec3(b[1] as number, b[0] as number, radius));
            }
          }
        }
        const g = new THREE.BufferGeometry();
        g.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
        setGeometry(g);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [radius]);

  if (!geometry) return null;
  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial color="#5f8fb5" transparent opacity={0.75} />
    </lineSegments>
  );
}

export function Graticule({ radius = 2.005 }: { radius?: number }) {
  const [geometry] = useState(() => {
    const positions: number[] = [];
    for (let lat = -60; lat <= 60; lat += 30) {
      for (let lon = -180; lon < 180; lon += 4) {
        positions.push(...latLonToVec3(lat, lon, radius));
        positions.push(...latLonToVec3(lat, lon + 4, radius));
      }
    }
    for (let lon = -180; lon < 180; lon += 30) {
      for (let lat = -88; lat < 88; lat += 4) {
        positions.push(...latLonToVec3(lat, lon, radius));
        positions.push(...latLonToVec3(lat + 4, lon, radius));
      }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    return g;
  });

  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial color="#2a3a48" transparent opacity={0.4} />
    </lineSegments>
  );
}
