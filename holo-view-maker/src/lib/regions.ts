export const REGIONS = [
  {
    id: "global",
    label: "Global (Planetary Overview)",
    bbox: [-180, -90, 180, 90],
    center: [0, 15],
    zoom: 1.6,
    pitch: 0,
  },
  {
    id: "india",
    label: "India (National)",
    bbox: [68, 6, 98, 38],
    center: [82.5, 22.5],
    zoom: 4.2,
    pitch: 25,
  },
  {
    id: "middle-east",
    label: "Middle East / Persian Gulf",
    bbox: [25, 12, 65, 42],
    center: [48.5, 26.5],
    zoom: 4.8,
    pitch: 35,
  },
  {
    id: "north-america",
    label: "North America",
    bbox: [-170, 5, -50, 84],
    center: [-95, 32],
    zoom: 4.2,
    pitch: 30,
  },
  {
    id: "south-america",
    label: "South America",
    bbox: [-82, -56, -34, 13],
    center: [-58, -20],
    zoom: 2.5,
    pitch: 0,
  },
  { id: "europe", label: "Europe", bbox: [-25, 34, 45, 72], center: [10, 52], zoom: 3, pitch: 0 },
  {
    id: "southeast-asia",
    label: "Southeast Asia",
    bbox: [92, -12, 142, 29],
    center: [117, 8],
    zoom: 3,
    pitch: 0,
  },
  { id: "africa", label: "Africa", bbox: [-20, -35, 52, 38], center: [17, 1], zoom: 2.5, pitch: 0 },
  {
    id: "australia",
    label: "Australia",
    bbox: [112, -44, 154, -10],
    center: [122, -23],
    zoom: 4.2,
    pitch: 30,
  },
  {
    id: "south-asia",
    label: "South Asia",
    bbox: [60, 5, 98, 38],
    center: [78, 23],
    zoom: 3.8,
    pitch: 25,
  },
  {
    id: "jharkhand-odisha",
    label: "Jharkhand / Odisha",
    bbox: [83, 17, 88, 25],
    center: [85.5, 22],
    zoom: 6,
    pitch: 35,
  },
  {
    id: "permian",
    label: "US Permian Basin",
    bbox: [-106, 29, -100, 34],
    center: [-103, 31.5],
    zoom: 5.8,
    pitch: 30,
  },
  {
    id: "gulf-coast",
    label: "US Gulf Coast",
    bbox: [-98, 25, -87, 33],
    center: [-93, 29.5],
    zoom: 5.2,
    pitch: 30,
  },
  {
    id: "pilbara",
    label: "Australian Pilbara",
    bbox: [114, -25, 122, -19],
    center: [118, -22],
    zoom: 5.5,
    pitch: 30,
  },
] as const;

export type RegionId = (typeof REGIONS)[number]["id"];

export function regionById(id: string | null) {
  return REGIONS.find((region) => region.id === id) ?? REGIONS[1];
}

/** Geographic windows can overlap; they are not administrative boundaries. */
export function inRegion(latitude: number, longitude: number, id: RegionId): boolean {
  if (
    !Number.isFinite(latitude) ||
    !Number.isFinite(longitude) ||
    Math.abs(latitude) > 90 ||
    Math.abs(longitude) > 180
  )
    return false;
  const [west, south, east, north] = regionById(id).bbox;
  return latitude >= south && latitude <= north && longitude >= west && longitude <= east;
}

export function coverageLabel(meta: { scope?: string } | null): string {
  const scope = meta?.scope?.trim();
  if (!scope) return "India export (legacy coverage)";
  if (scope.toLowerCase() === "global") return "Global export";
  if (scope.toLowerCase() === "india" || scope.toLowerCase() === "national") return "India export";
  return `${scope} export`;
}
