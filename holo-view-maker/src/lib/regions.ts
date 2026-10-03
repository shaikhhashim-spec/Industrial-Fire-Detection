export const REGIONS = [
  {
    id: "global",
    label: "Global / Entire Earth",
    bbox: [-180, -90, 180, 90],
    center: [0, 15],
    zoom: 1.6,
  },
  { id: "india", label: "India", bbox: [68, 6, 98, 38], center: [82.5, 22.5], zoom: 3 },
  { id: "middle-east", label: "Middle East", bbox: [25, 12, 65, 42], center: [45, 27], zoom: 3 },
  {
    id: "north-america",
    label: "North America",
    bbox: [-170, 5, -50, 84],
    center: [-105, 45],
    zoom: 2,
  },
  {
    id: "south-america",
    label: "South America",
    bbox: [-82, -56, -34, 13],
    center: [-58, -20],
    zoom: 2.5,
  },
  { id: "europe", label: "Europe", bbox: [-25, 34, 45, 72], center: [10, 52], zoom: 3 },
  {
    id: "southeast-asia",
    label: "Southeast Asia",
    bbox: [92, -12, 142, 29],
    center: [117, 8],
    zoom: 3,
  },
  { id: "africa", label: "Africa", bbox: [-20, -35, 52, 38], center: [17, 1], zoom: 2.5 },
  { id: "australia", label: "Australia", bbox: [112, -44, 154, -10], center: [133, -27], zoom: 3 },
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
