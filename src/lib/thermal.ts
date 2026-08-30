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

export const RISK_COLORS: Record<RiskLevel, string> = {
  LOW: "#0ca30c",
  MODERATE: "#fab219",
  HIGH: "#ec835a",
  CRITICAL: "#e66767",
};

export interface ThermalEvent {
  id: string;
  region: string;
  latitude: number;
  longitude: number;
  category: Category;
  riskScore: number;
  riskLevel: RiskLevel;
  frp: number;
  brightness: number;
  confidence: number;
  persistenceDays: number;
  detectionCount: number;
  satellite: "VIIRS S-NPP" | "VIIRS NOAA-20" | "MODIS Aqua" | "MODIS Terra";
  daynight: "D" | "N";
  status: "NEW" | "RECURRING" | "PERSISTENT" | "HIGH RISK" | "CRITICAL";
  acqDate: string;
  history: { date: string; frp: number; confidence: number }[];
}

const CATEGORIES = Object.keys(CATEGORY_COLORS) as Category[];
const SATS: ThermalEvent["satellite"][] = [
  "VIIRS S-NPP",
  "VIIRS NOAA-20",
  "MODIS Aqua",
  "MODIS Terra",
];

/** Industrial / thermal corridors used as cluster seeds. */
const SEEDS: { name: string; lat: number; lon: number; n: number }[] = [
  { name: "Jamshedpur–Bokaro Belt", lat: 22.8, lon: 86.2, n: 9 },
  { name: "Angul–Talcher Corridor", lat: 20.95, lon: 85.1, n: 7 },
  { name: "Raigarh–Korba Basin", lat: 22.0, lon: 82.8, n: 7 },
  { name: "Jamnagar Refinery Zone", lat: 22.35, lon: 69.9, n: 6 },
  { name: "Vishakhapatnam Coast", lat: 17.7, lon: 83.2, n: 5 },
  { name: "Punjab Stubble Belt", lat: 30.6, lon: 75.5, n: 10 },
  { name: "Bhilai–Durg Works", lat: 21.2, lon: 81.4, n: 5 },
  { name: "Mumbai–Thane Industrial", lat: 19.2, lon: 73.0, n: 6 },
  { name: "Kutch Salt & Power", lat: 23.4, lon: 70.5, n: 4 },
  { name: "Uttarakhand Forest Line", lat: 30.1, lon: 79.0, n: 5 },
  { name: "Barauni–Begusarai", lat: 25.5, lon: 86.0, n: 4 },
  { name: "Chennai Manali Cluster", lat: 13.16, lon: 80.26, n: 5 },
];

function mulberry32(seed: number) {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function riskLevel(score: number): RiskLevel {
  if (score >= 80) return "CRITICAL";
  if (score >= 60) return "HIGH";
  if (score >= 35) return "MODERATE";
  return "LOW";
}

function buildEvents(): ThermalEvent[] {
  const rnd = mulberry32(26162);
  const events: ThermalEvent[] = [];
  const base = Date.UTC(2026, 7, 30);

  SEEDS.forEach((seed, si) => {
    for (let i = 0; i < seed.n; i++) {
      const lat = seed.lat + (rnd() - 0.5) * 1.6;
      const lon = seed.lon + (rnd() - 0.5) * 1.8;
      const agri = seed.name.includes("Stubble");
      const forest = seed.name.includes("Forest");
      const category: Category = agri
        ? rnd() > 0.25
          ? "Likely Agricultural Burning"
          : "Requires Verification"
        : forest
          ? rnd() > 0.35
            ? "Likely Wildfire"
            : "Persistent Non-Industrial Thermal Source"
          : CATEGORIES[Math.floor(rnd() * 5)];

      const persistenceDays = Math.round(1 + rnd() * 26);
      const frp = Math.round((3 + rnd() * 180) * 10) / 10;
      const confidence = Math.round(35 + rnd() * 64);
      const detectionCount = Math.round(persistenceDays * (0.8 + rnd() * 2.4));
      const riskScore = Math.min(
        99,
        Math.round(
          0.34 * Math.min(100, persistenceDays * 4) +
            0.28 * Math.min(100, frp / 1.8) +
            0.22 * confidence +
            0.16 * Math.min(100, detectionCount * 2.5),
        ),
      );
      const level = riskLevel(riskScore);
      const days = Math.min(12, persistenceDays);
      const history = Array.from({ length: days }, (_, d) => ({
        date: new Date(base - (days - 1 - d) * 86400000).toISOString().slice(0, 10),
        frp: Math.round(frp * (0.45 + rnd() * 1.1) * 10) / 10,
        confidence: Math.max(20, Math.min(100, Math.round(confidence + (rnd() - 0.5) * 30))),
      }));

      events.push({
        id: `TI-${String(si + 1).padStart(2, "0")}${String(i + 1).padStart(2, "0")}`,
        region: seed.name,
        latitude: Math.round(lat * 10000) / 10000,
        longitude: Math.round(lon * 10000) / 10000,
        category,
        riskScore,
        riskLevel: level,
        frp,
        brightness: Math.round(298 + rnd() * 90),
        confidence,
        persistenceDays,
        detectionCount,
        satellite: SATS[Math.floor(rnd() * SATS.length)],
        daynight: rnd() > 0.45 ? "N" : "D",
        status:
          level === "CRITICAL"
            ? "CRITICAL"
            : level === "HIGH"
              ? "HIGH RISK"
              : persistenceDays > 14
                ? "PERSISTENT"
                : persistenceDays > 5
                  ? "RECURRING"
                  : "NEW",
        acqDate: new Date(base - Math.floor(rnd() * 3) * 86400000).toISOString().slice(0, 10),
        history,
      });
    }
  });

  return events.sort((a, b) => b.riskScore - a.riskScore);
}

export const THERMAL_EVENTS: ThermalEvent[] = buildEvents();

/** Convert lat/lon to a point on a sphere of given radius (three.js Y-up). */
export function latLonToVec3(lat: number, lon: number, radius: number): [number, number, number] {
  const phi = (90 - lat) * (Math.PI / 180);
  const theta = (lon + 180) * (Math.PI / 180);
  return [
    -radius * Math.sin(phi) * Math.cos(theta),
    radius * Math.cos(phi),
    radius * Math.sin(phi) * Math.sin(theta),
  ];
}
