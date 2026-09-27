/** One small, hand-drawn icon set shared by the nav and every page's section
 * headers — 24x24, stroke-only, currentColor, matching the dashboard's own
 * icon style. No icon library: this is the whole set the site needs. */
import { h } from "./dom.mjs";

function svg(...paths) {
  return h("svg", { viewBox: "0 0 24 24", "aria-hidden": "true" }, ...paths);
}
const path = (d) => h("path", { d });
const rect = (x, y, w, ht) => h("rect", { x, y, width: w, height: ht, rx: "1" });
const circle = (cx, cy, r) => h("circle", { cx, cy, r });

export const ICON = {
  overview: () => svg(rect(3, 3, 7, 18), rect(14, 3, 7, 8), rect(14, 14, 7, 7)),
  map: () => svg(path("M9 4 4 6v14l5-2 6 2 5-2V6l-5 2-6-2Z"), path("M9 4v14M15 6v14")),
  globe: () => svg(circle(12, 12, 9), path("M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18")),
  events: () => svg(path("M12 2c0 4-1 7-3 9s-5 3-9 3c4 0 7 1 9 3s3 5 3 9c0-4 1-7 3-9s5-3 9-3c-4 0-7-1-9-3s-3-5-3-9Z")),
  bell: () => svg(path("M6 16v-5a6 6 0 1 1 12 0v5l2 2H4l2-2zM10 21h4")),
  analytics: () => svg(rect(4, 12, 3, 8), rect(10, 7, 3, 13), rect(16, 3, 3, 17)),
  search: () => svg(circle(10, 10, 6), path("M20 20l-5.2-5.2")),
  settings: () =>
    svg(
      path("M4 6h9M17 6h3M4 12h4M12 12h8M4 18h11M19 18h1"),
      circle(15, 6, 2),
      circle(8, 12, 2),
      circle(17, 18, 2),
    ),
  warning: () => svg(path("M12 3 2 20h20L12 3Z"), path("M12 9.5v4.5"), path("M12 17h.01")),
  list: () =>
    svg(
      path("M5 6h.01"),
      path("M9 6h11"),
      path("M5 12h.01"),
      path("M9 12h11"),
      path("M5 18h.01"),
      path("M9 18h11"),
    ),
  refresh: () => svg(path("M4 12a8 8 0 0 1 14-5.3M20 12a8 8 0 0 1-14 5.3"), path("M18 3.5V8h-4"), path("M6 20.5V16h4")),
  clock: () => svg(circle(12, 12, 9), path("M12 7v5l4 2")),
  tag: () => svg(path("M4 4h7l9 9-7 7-9-9V4Z"), circle(8, 8, 1.3)),
  pulse: () => svg(path("M2 12h4l2-7 4 14 3-9 2 4h5")),
  calendar: () => svg(rect(3, 4, 18, 17), path("M3 9h18M8 2v4M16 2v4")),
  pin: () => svg(path("M12 21s7-7.2 7-12a7 7 0 1 0-14 0c0 4.8 7 12 7 12Z"), circle(12, 9, 2.3)),
  signal: () => svg(circle(12, 18, 1.4), path("M9 15a4.2 4.2 0 0 1 6 0"), path("M6 12a8.4 8.4 0 0 1 12 0")),
  download: () => svg(path("M12 3v13M7 11l5 5 5-5"), path("M5 21h14")),
  lock: () => svg(rect(5, 11, 14, 9), path("M8 11V8a4 4 0 0 1 8 0v3")),
};
