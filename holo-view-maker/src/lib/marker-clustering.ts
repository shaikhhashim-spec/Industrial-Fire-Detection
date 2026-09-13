import { type ThermalEvent } from "@/lib/thermal";

export interface Cluster {
  key: string;
  latitude: number;
  longitude: number;
  events: ThermalEvent[];
}

/**
 * Groups nearby thermal detections into distinct spatial clusters for clean 3D globe presentation,
 * preventing noisy overlapping blobs and rendering majestic vertical beams with aggregate telemetry.
 */
export function planMarkerRender(events: ThermalEvent[]): { visible: Cluster[] } {
  if (!events || events.length === 0) return { visible: [] };

  const CLUSTER_GRID_DEG = 0.55;
  const clustersMap = new Map<string, ThermalEvent[]>();

  events.forEach((event) => {
    const latBin = Math.round(event.latitude / CLUSTER_GRID_DEG);
    const lonBin = Math.round(event.longitude / CLUSTER_GRID_DEG);
    const key = `${latBin}_${lonBin}`;
    if (!clustersMap.has(key)) {
      clustersMap.set(key, []);
    }
    clustersMap.get(key)!.push(event);
  });

  const clusters: Cluster[] = [];
  clustersMap.forEach((evList, key) => {
    const avgLat = evList.reduce((acc, e) => acc + e.latitude, 0) / evList.length;
    const avgLon = evList.reduce((acc, e) => acc + e.longitude, 0) / evList.length;
    clusters.push({
      key,
      latitude: avgLat,
      longitude: avgLon,
      events: evList,
    });
  });

  // Sort by highest risk score in each cluster so primary beacons render with high priority
  clusters.sort((a, b) => {
    const maxA = Math.max(...a.events.map((e) => e.riskScore));
    const maxB = Math.max(...b.events.map((e) => e.riskScore));
    return maxB - maxA;
  });

  return { visible: clusters };
}
