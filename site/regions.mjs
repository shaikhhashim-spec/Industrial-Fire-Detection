// Geographic windows, kept aligned with the globe's lib/regions.ts.
export const REGIONS = [
  { id: "global", label: "Global / Entire Earth", bbox: [-180, -90, 180, 90] },
  { id: "india", label: "India", bbox: [68, 6, 98, 38] },
  { id: "middle-east", label: "Middle East", bbox: [25, 12, 65, 42] },
  { id: "north-america", label: "North America", bbox: [-170, 5, -50, 84] },
  { id: "south-america", label: "South America", bbox: [-82, -56, -34, 13] },
  { id: "europe", label: "Europe", bbox: [-25, 34, 45, 72] },
  { id: "southeast-asia", label: "Southeast Asia", bbox: [92, -12, 142, 29] },
  { id: "africa", label: "Africa", bbox: [-20, -35, 52, 38] },
  { id: "australia", label: "Australia", bbox: [112, -44, 154, -10] },
];

export function regionById(id) {
  return REGIONS.find((region) => region.id === id) ?? REGIONS[1];
}

export function inRegion(event, id) {
  const { latitude: lat, longitude: lon } = event;
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) return false;
  const [west, south, east, north] = regionById(id).bbox;
  return lat >= south && lat <= north && lon >= west && lon <= east;
}
