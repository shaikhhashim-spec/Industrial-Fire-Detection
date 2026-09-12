import { subsolarPoint } from "@/lib/sun";

const DEG = Math.PI / 180;
const MERC_MAX_LAT = 85.051129;

/** Corners of the whole Web-Mercator world, for a MapLibre image source. */
export const NIGHT_COORDS: [
  [number, number],
  [number, number],
  [number, number],
  [number, number],
] = [
  [-180, MERC_MAX_LAT],
  [180, MERC_MAX_LAT],
  [180, -MERC_MAX_LAT],
  [-180, -MERC_MAX_LAT],
];

function smoothstep(a: number, b: number, x: number): number {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
}

/**
 * Paints live day/night shading into `canvas`: the night side darkened through
 * civil and nautical twilight (full dark once the sun is 12° below the
 * horizon), a warm dusk band, and a thin glowing terminator. Rows are laid out
 * in Web-Mercator y, because an image source is stretched linearly in Mercator
 * space — an equirectangular image would put the terminator at the wrong
 * latitude.
 */
export function paintNight(canvas: HTMLCanvasElement, date: Date, size = 1024): HTMLCanvasElement {
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  const img = ctx.createImageData(size, size);
  const px = img.data;

  const sun = subsolarPoint(date);
  const sLat = sun.lat * DEG;
  const sLon = sun.lon * DEG;
  const sx = Math.cos(sLat) * Math.cos(sLon);
  const sy = Math.cos(sLat) * Math.sin(sLon);
  const sz = Math.sin(sLat);

  const cosLon = new Float64Array(size);
  const sinLon = new Float64Array(size);
  for (let x = 0; x < size; x++) {
    const lon = (((x + 0.5) / size) * 360 - 180) * DEG;
    cosLon[x] = Math.cos(lon);
    sinLon[x] = Math.sin(lon);
  }

  for (let y = 0; y < size; y++) {
    const my = Math.PI - ((y + 0.5) / size) * 2 * Math.PI; // Mercator y, top = +π
    const lat = Math.atan(Math.sinh(my));
    const cl = Math.cos(lat);
    const sl = Math.sin(lat);
    for (let x = 0; x < size; x++) {
      // sine of the solar elevation at this pixel
      const s = cl * (cosLon[x]! * sx + sinLon[x]! * sy) + sl * sz;
      if (s > 0.07) continue; // full daylight: leave transparent

      // night: near-black navy, deepening through twilight
      let a = 0.6 * (1 - smoothstep(-0.21, 0, s));
      let r = 0;
      let g = 4;
      let b = 16;

      // dusk band: warm glow just either side of the terminator
      const dusk = smoothstep(-0.21, -0.02, s) * (1 - smoothstep(-0.02, 0.07, s)) * 0.16;
      if (dusk > 0) {
        const na = dusk + a * (1 - dusk);
        r = (255 * dusk + r * a * (1 - dusk)) / na;
        g = (140 * dusk + g * a * (1 - dusk)) / na;
        b = (56 * dusk + b * a * (1 - dusk)) / na;
        a = na;
      }

      // terminator line
      if (Math.abs(s) < 0.03) {
        const line = Math.exp(-((s / 0.0075) ** 2)) * 0.7;
        const na = line + a * (1 - line);
        r = (255 * line + r * a * (1 - line)) / na;
        g = (176 * line + g * a * (1 - line)) / na;
        b = (86 * line + b * a * (1 - line)) / na;
        a = na;
      }

      const i = (y * size + x) * 4;
      px[i] = r;
      px[i + 1] = g;
      px[i + 2] = b;
      px[i + 3] = a * 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  return canvas;
}
