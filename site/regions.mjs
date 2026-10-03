// Geographic windows, kept aligned with the globe's lib/regions.ts.
export const REGIONS = [
  { id: "global", label: "Global (Planetary Overview)", bbox: [-180, -90, 180, 90] },
  { id: "india", label: "India (National)", bbox: [68, 6, 98, 38] },
  { id: "middle-east", label: "Middle East / Persian Gulf", bbox: [25, 12, 65, 42] },
  { id: "north-america", label: "North America", bbox: [-170, 5, -50, 84] },
  { id: "south-america", label: "South America", bbox: [-82, -56, -34, 13] },
  { id: "europe", label: "Europe", bbox: [-25, 34, 45, 72] },
  { id: "southeast-asia", label: "Southeast Asia", bbox: [92, -12, 142, 29] },
  { id: "africa", label: "Africa", bbox: [-20, -35, 52, 38] },
  { id: "australia", label: "Australia", bbox: [112, -44, 154, -10] },
  { id: "south-asia", label: "South Asia", bbox: [60, 5, 98, 38] },
  { id: "jharkhand-odisha", label: "Jharkhand / Odisha", bbox: [83, 17, 88, 25] },
  { id: "permian", label: "US Permian Basin", bbox: [-106, 29, -100, 34] },
  { id: "gulf-coast", label: "US Gulf Coast", bbox: [-98, 25, -87, 33] },
  { id: "pilbara", label: "Australian Pilbara", bbox: [114, -25, 122, -19] },
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
