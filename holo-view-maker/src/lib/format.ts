const timeOpts: Intl.DateTimeFormatOptions = { hour: "2-digit", minute: "2-digit", hour12: false };

export function fmtUtc(d: Date, seconds = false): string {
  return d.toLocaleTimeString("en-GB", {
    ...timeOpts,
    second: seconds ? "2-digit" : undefined,
    timeZone: "UTC",
  });
}

export function fmtIst(d: Date, seconds = false): string {
  return d.toLocaleTimeString("en-GB", {
    ...timeOpts,
    second: seconds ? "2-digit" : undefined,
    timeZone: "Asia/Kolkata",
  });
}

/** "in 1h 04m", "in 12m", "now" — for a future instant. */
export function fmtIn(target: Date, now: Date): string {
  const min = Math.round((target.getTime() - now.getTime()) / 60000);
  if (min <= 0) return "now";
  if (min < 60) return `in ${min}m`;
  return `in ${Math.floor(min / 60)}h ${String(min % 60).padStart(2, "0")}m`;
}

/** "3 min ago", "5 h ago", "2 d ago" — for a past instant. */
export function fmtAgo(ms: number, now = Date.now()): string {
  const min = Math.max(0, Math.round((now - ms) / 60000));
  if (min < 60) return `${min} min ago`;
  if (min < 48 * 60) return `${Math.round(min / 60)} h ago`;
  return `${Math.round(min / 1440)} d ago`;
}

export function fmtLat(lat: number): string {
  return `${Math.abs(lat).toFixed(2)}°${lat >= 0 ? "N" : "S"}`;
}

export function fmtLon(lon: number): string {
  return `${Math.abs(lon).toFixed(2)}°${lon >= 0 ? "E" : "W"}`;
}
