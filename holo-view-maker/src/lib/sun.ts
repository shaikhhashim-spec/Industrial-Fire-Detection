const DEG = Math.PI / 180;

/**
 * Point on Earth where the sun is directly overhead, from the low-precision
 * Astronomical Almanac solar formulae (~0.01° over 1950–2050). Unlike a plain
 * "12:00 UTC is 0° longitude" estimate this includes the equation of time,
 * which moves the terminator by up to ~4° of longitude over the year.
 */
export function subsolarPoint(date: Date): { lat: number; lon: number } {
  const d = date.getTime() / 86400000 - 10957.5; // days since J2000.0
  const g = (357.529 + 0.98560028 * d) * DEG; // mean anomaly
  const q = 280.459 + 0.98564736 * d; // mean longitude
  const eclLon = (q + 1.915 * Math.sin(g) + 0.02 * Math.sin(2 * g)) * DEG;
  const obliquity = (23.439 - 0.00000036 * d) * DEG;
  const ra = Math.atan2(Math.cos(obliquity) * Math.sin(eclLon), Math.cos(eclLon));
  const dec = Math.asin(Math.sin(obliquity) * Math.sin(eclLon));
  const gmst = 280.46061837 + 360.98564736629 * d;
  const lon = ((((ra / DEG - gmst + 180) % 360) + 360) % 360) - 180;
  return { lat: dec / DEG, lon };
}

/** Solar elevation angle in degrees at a location (negative = sun below horizon). */
export function sunElevation(lat: number, lon: number, date: Date): number {
  const s = subsolarPoint(date);
  const cosZenith =
    Math.sin(lat * DEG) * Math.sin(s.lat * DEG) +
    Math.cos(lat * DEG) * Math.cos(s.lat * DEG) * Math.cos((lon - s.lon) * DEG);
  return 90 - Math.acos(Math.max(-1, Math.min(1, cosZenith))) / DEG;
}
