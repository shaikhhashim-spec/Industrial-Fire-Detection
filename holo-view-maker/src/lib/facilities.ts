import type { ExpressionSpecification } from "maplibre-gl";

/** Colour per facility kind (kinds come from scripts/build_india_reference.py). */
export const FACILITY_COLORS: Record<string, string> = {
  "steel / iron works": "#93c5fd",
  "thermal power plant": "#facc15",
  "refinery / oil & gas": "#fb923c",
  smelter: "#c084fc",
  "coke oven": "#fca5a5",
  "cement plant": "#e7e5e4",
  "coal mine": "#a8a29e",
  "brick kiln": "#f87171",
  "chemical / fertilizer plant": "#34d399",
  "mine / quarry": "#78716c",
  "industrial works": "#64748b",
};

/** The kinds worth a legend row — the big, known heat sources. */
export const FACILITY_LEGEND = [
  "steel / iron works",
  "thermal power plant",
  "refinery / oil & gas",
  "cement plant",
  "coal mine",
  "brick kiln",
];

// built dynamically from the table above, which the literal expression type
// can't follow — hence the cast through unknown
export const FACILITY_COLOR_EXPR = [
  "match",
  ["get", "kind"],
  ...Object.entries(FACILITY_COLORS).flat(),
  "#64748b",
] as unknown as ExpressionSpecification;
