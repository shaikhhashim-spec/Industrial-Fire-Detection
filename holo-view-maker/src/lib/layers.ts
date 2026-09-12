import { fmtAgo } from "@/lib/format";

export type LayerKey =
  | "detections"
  | "facilities"
  | "sats"
  | "swath"
  | "quakes"
  | "eonet"
  | "daynight"
  | "imagery"
  | "borders"
  | "graticule";

export type Layers = Record<LayerKey, boolean>;

export const DEFAULT_LAYERS: Layers = {
  detections: true,
  facilities: true,
  sats: true,
  swath: false,
  quakes: true,
  eonet: true,
  daynight: true,
  imagery: false,
  borders: true,
  graticule: true,
};

export type FeedStatus = "loading" | "ok" | "fallback" | "error";

export interface FeedState {
  status: FeedStatus;
  count: number;
  updatedAt: number | null;
  /** Short human note: "cached 2 h ago", the error message, … */
  note?: string;
}

/** Health marker colours shared by the layer panel and status bar. Every use
 * sits next to a word, so colour is never the only thing carrying the state. */
export const STATUS_DOT: Record<FeedStatus, string> = {
  loading: "bg-muted-foreground",
  ok: "bg-[var(--ok)]",
  fallback: "bg-[var(--warn)]",
  error: "bg-[var(--critical)]",
};

export function feedTitle(feed: FeedState): string {
  const when = feed.updatedAt ? `, updated ${fmtAgo(feed.updatedAt)}` : "";
  return `${feed.status}${when}${feed.note ? `, ${feed.note}` : ""}`;
}

export interface LayerDef {
  key: LayerKey;
  label: string;
  description?: string;
  shortcut: string;
  /** A modifier of another layer, drawn indented and inert while its parent is off. */
  parent?: LayerKey;
}

export interface LayerGroupDef {
  label: string;
  layers: LayerDef[];
}

export const LAYER_GROUPS: LayerGroupDef[] = [
  {
    label: "Thermal",
    layers: [
      {
        key: "detections",
        label: "Detections",
        description: "FIRMS pipeline hotspots",
        shortcut: "T",
      },
      {
        key: "facilities",
        label: "Industrial sites",
        description: "OpenStreetMap and WRI, the why behind a cluster",
        shortcut: "F",
      },
    ],
  },
  {
    label: "Orbital",
    layers: [
      {
        key: "sats",
        label: "Fire satellites",
        description: "VIIRS and MODIS live orbits",
        shortcut: "S",
      },
      {
        key: "swath",
        label: "Swath footprints",
        description: "Ground area each sensor sees now",
        shortcut: "W",
        parent: "sats",
      },
    ],
  },
  {
    label: "Hazard context",
    layers: [
      {
        key: "quakes",
        label: "Earthquakes",
        description: "USGS, magnitude 2.5 and above, past 7 days",
        shortcut: "E",
      },
      {
        key: "eonet",
        label: "Natural events",
        description: "NASA EONET, open wildfires, storms and volcanoes",
        shortcut: "N",
      },
    ],
  },
  {
    label: "Display",
    layers: [
      {
        key: "daynight",
        label: "Day and night",
        description: "Live solar terminator",
        shortcut: "D",
      },
      {
        key: "imagery",
        label: "Satellite imagery",
        description: "Esri World Imagery, for zooming in on a site",
        shortcut: "I",
      },
      { key: "borders", label: "Country borders", shortcut: "B" },
      { key: "graticule", label: "Graticule", shortcut: "G" },
    ],
  },
];

export const SHORTCUT_TO_LAYER: Record<string, LayerKey> = Object.fromEntries(
  LAYER_GROUPS.flatMap((g) => g.layers.map((l) => [l.shortcut.toLowerCase(), l.key])),
);
