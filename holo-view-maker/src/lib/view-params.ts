/** A view named in the page address, e.g. `?lat=12.97&lon=77.59&z=15`, so a link
 * can open the globe on a place. Anything missing or out of range is ignored. */
export function viewFromUrl(): { center: [number, number]; zoom: number } | null {
  const q = new URLSearchParams(window.location.search);
  if (!q.has("lat") || !q.has("lon")) return null;
  const lat = Number(q.get("lat"));
  const lon = Number(q.get("lon"));
  const zoom = q.has("z") ? Number(q.get("z")) : 5;
  if (![lat, lon, zoom].every(Number.isFinite)) return null;
  if (Math.abs(lat) > 85 || Math.abs(lon) > 180 || zoom < 1 || zoom > 18) return null;
  return { center: [lon, lat], zoom };
}
