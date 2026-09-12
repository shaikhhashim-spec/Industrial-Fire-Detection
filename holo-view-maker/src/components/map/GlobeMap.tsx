/*
 * MapLibre GL globe, built the way OSIRIS builds its map
 * (github.com/simplifaisoul/osiris, MIT): globe projection over CARTO's Dark
 * Matter vector basemap, with every data set drawn as a GPU style layer — one
 * draw for all 7,500+ hotspots instead of one scene object each.
 */
import { useEffect, useRef, useState } from "react";
import {
  Map as MLMap,
  Marker,
  Popup,
  getVersion,
  setWorkerUrl,
  type ExpressionSpecification,
  type GeoJSONSource,
  type ImageSource,
  type MapGeoJSONFeature,
} from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { GeoJSON } from "geojson";
import type { ThermalEvent } from "@/lib/thermal";
import type { LayerKey, Layers } from "@/lib/layers";
import type { FireSat } from "@/lib/satellites";
import type { Hazard } from "@/lib/hazards";
import { cursorStore } from "@/lib/globe-store";
import { fmtAgo } from "@/lib/format";
import {
  EMPTY_FC,
  eventsToGeoJSON,
  graticuleGeoJSON,
  hazardsGeoJSON,
  satPointsGeoJSON,
  satPositions,
  satTracksGeoJSON,
  stormTracksGeoJSON,
  swathGeoJSON,
} from "@/lib/geo-layers";
import { NIGHT_COORDS, paintNight } from "@/lib/night-raster";
import { FACILITY_COLOR_EXPR } from "@/lib/facilities";

// Same font stack the CARTO style itself uses, so its glyph server has it.
const LABEL_FONT = ["Montserrat Regular", "Open Sans Regular", "Noto Sans Regular"];

// Self-hosted by scripts/prepare-map-worker.mjs (runs before dev and build): the
// bundled worker URL breaks under Vite, leaving vector tiles and GeoJSON undrawn.
setWorkerUrl(`/vendor/maplibre/${getVersion()}/maplibre-gl-worker.mjs`);

const DARK_STYLE = "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json";
const IMAGERY_TILES =
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";
const START_CENTER: [number, number] = [82.5, 22.5];
/** Degrees of longitude per second while auto-rotating. */
const SPIN_DEG_PER_SEC = 2.5;

/** Zoom at which the whole globe fits the container with a margin. MapLibre
 * zoom is absolute (tile pixels), so a fixed value crops the globe in a small
 * frame such as the Streamlit iframe; zoom 2.35 fits an ~800 px-high panel. */
function fitZoom(el: HTMLElement): number {
  const size = Math.min(el.clientWidth, el.clientHeight) || 800;
  return Math.min(3.2, Math.max(1, 2.35 + Math.log2(size / 800)));
}

export interface GlobeMapProps {
  events: ThermalEvent[];
  selectedId: string | null;
  colorBy: "category" | "risk";
  spin: boolean;
  onSelect: (id: string) => void;
  layers: Layers;
  sats: FireSat[];
  quakes: Hazard[];
  naturalEvents: Hazard[];
  selectedHazard: Hazard | null;
  onSelectHazard: (h: Hazard) => void;
  /** The user grabbed the map, so stop auto-rotating. */
  onInteract: () => void;
}

/** Style layers behind each panel toggle. Basemap boundary layers are found at load. */
const LAYER_IDS: Record<Exclude<LayerKey, "borders">, string[]> = {
  detections: ["thermal-heat", "thermal-glow", "thermal", "thermal-selected"],
  sats: ["sat-track-past", "sat-track-ahead", "sat-glow", "sat-core"],
  swath: ["sat-swath-fill", "sat-swath-line"],
  quakes: ["quake-pulse", "quakes"],
  eonet: ["eonet-tracks", "eonet"],
  daynight: ["night"],
  graticule: ["graticule"],
  imagery: ["imagery"],
  facilities: ["facilities", "facility-labels"],
};

// topmost first: a hotspot sitting on a plant should pick the hotspot
const INTERACTIVE = ["sat-core", "thermal", "quakes", "eonet", "facilities"];

// Transparent at low density on purpose: scattered single detections should read
// as dots, and only real clusters (steel plants, coalfields) should glow.
const HEAT_RAMP: ExpressionSpecification = [
  "interpolate",
  ["linear"],
  ["heatmap-density"],
  0,
  "rgba(0,0,0,0)",
  0.18,
  "rgba(120,20,8,0)",
  0.35,
  "rgba(185,40,14,0.5)",
  0.55,
  "rgba(240,95,28,0.78)",
  0.78,
  "rgba(255,175,65,0.92)",
  1,
  "rgba(255,242,205,1)",
];

function colorExpr(by: "category" | "risk"): ExpressionSpecification {
  return ["get", by === "category" ? "catColor" : "riskColor"];
}

function setData(map: MLMap, id: string, data: GeoJSON) {
  (map.getSource(id) as GeoJSONSource | undefined)?.setData(data);
}

function esc(s: string): string {
  return s.replace(
    /[&<>"]/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]!,
  );
}

function installLayers(map: MLMap, colorBy: "category" | "risk") {
  const style = map.getStyle().layers;
  // Imagery and the night shade sit above the basemap fills and roads but under
  // country borders and place labels, so both stay readable on top.
  const underBorders =
    style.find((l) => l.id === "boundary_country_outline")?.id ??
    style.find((l) => l.type === "symbol")?.id;
  const underLabels = style.find((l) => l.type === "symbol")?.id;

  // Tint the basemap's borders toward the dashboard's cyan.
  for (const id of ["boundary_country_outline", "boundary_country_inner"]) {
    if (map.getLayer(id)) {
      map.setPaintProperty(id, "line-color", "#2f6f8f");
      map.setPaintProperty(id, "line-opacity", 0.75);
    }
  }

  map.addSource("imagery", {
    type: "raster",
    tiles: [IMAGERY_TILES],
    tileSize: 256,
    maxzoom: 19,
    attribution: "Imagery © Esri, Maxar, Earthstar Geographics",
  });
  map.addLayer(
    { id: "imagery", type: "raster", source: "imagery", layout: { visibility: "none" } },
    underBorders,
  );

  map.addSource("night", { type: "image", coordinates: NIGHT_COORDS });
  map.addLayer(
    {
      id: "night",
      type: "raster",
      source: "night",
      paint: { "raster-fade-duration": 0, "raster-resampling": "linear" },
    },
    underBorders,
  );

  map.addSource("graticule", { type: "geojson", data: graticuleGeoJSON() });
  map.addLayer(
    {
      id: "graticule",
      type: "line",
      source: "graticule",
      paint: { "line-color": "#1f5670", "line-width": 0.6, "line-opacity": 0.4 },
    },
    underLabels,
  );

  // ── hazard context: open natural events, then earthquakes on top ──
  map.addSource("eonet-tracks", { type: "geojson", data: EMPTY_FC });
  map.addLayer({
    id: "eonet-tracks",
    type: "line",
    source: "eonet-tracks",
    paint: {
      "line-color": ["get", "color"],
      "line-width": 1.2,
      "line-opacity": 0.6,
      "line-dasharray": [2, 1.5],
    },
  });
  map.addSource("eonet", { type: "geojson", data: EMPTY_FC });
  map.addLayer({
    id: "eonet",
    type: "circle",
    source: "eonet",
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 1, 2.2, 6, 5, 10, 7],
      "circle-color": ["get", "color"],
      "circle-opacity": 0.8,
      "circle-stroke-color": "#0a0e13",
      "circle-stroke-width": 0.8,
    },
  });

  map.addSource("quakes", { type: "geojson", data: EMPTY_FC });
  // The pulse marks quakes from the past 24 h. It is an age encoding the
  // legend names, not an attention-grabbing animation for its own sake.
  map.addLayer({
    id: "quake-pulse",
    type: "circle",
    source: "quakes",
    filter: ["==", ["get", "recent"], true],
    paint: {
      "circle-radius": 8,
      "circle-color": "rgba(0,0,0,0)",
      "circle-stroke-color": ["get", "color"],
      "circle-stroke-width": 1,
      "circle-stroke-opacity": 0.5,
    },
  });
  const magAbove = ["max", 0, ["-", ["get", "mag"], 2.5]] as ExpressionSpecification;
  map.addLayer({
    id: "quakes",
    type: "circle",
    source: "quakes",
    paint: {
      "circle-radius": [
        "interpolate",
        ["linear"],
        ["zoom"],
        1,
        ["+", 1.6, ["*", magAbove, 1.2]],
        6,
        ["+", 4, ["*", magAbove, 3]],
      ],
      "circle-color": ["get", "color"],
      "circle-opacity": 0.2,
      "circle-stroke-color": ["get", "color"],
      "circle-stroke-width": 1.1,
      "circle-stroke-opacity": 0.9,
    },
  });

  map.addSource("hazard-selected", { type: "geojson", data: EMPTY_FC });
  map.addLayer({
    id: "hazard-selected",
    type: "circle",
    source: "hazard-selected",
    paint: {
      "circle-radius": 13,
      "circle-color": "rgba(0,0,0,0)",
      "circle-stroke-color": "#e4eaf0",
      "circle-stroke-width": 1.6,
    },
  });

  // ── known industrial sites (OSM + WRI): the "why" behind hotspot clusters ──
  map.addSource("facilities", { type: "geojson", data: "/data/facilities.geojson" });
  map.addLayer({
    id: "facilities",
    type: "circle",
    source: "facilities",
    minzoom: 4.5,
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, 1.8, 8, 3.5, 12, 6],
      "circle-color": "#0b1016",
      "circle-stroke-color": FACILITY_COLOR_EXPR,
      "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 5, 1, 10, 1.8],
      "circle-opacity": ["interpolate", ["linear"], ["zoom"], 4.5, 0, 5.5, 0.9],
      "circle-stroke-opacity": ["interpolate", ["linear"], ["zoom"], 4.5, 0, 5.5, 0.9],
    },
  });
  map.addLayer({
    id: "facility-labels",
    type: "symbol",
    source: "facilities",
    minzoom: 8.5,
    filter: ["!=", ["get", "name"], ""],
    layout: {
      "text-field": ["get", "name"],
      "text-font": LABEL_FONT,
      "text-size": 10,
      "text-offset": [0, 1.1],
      "text-anchor": "top",
      "text-max-width": 10,
      "text-optional": true,
    },
    paint: {
      "text-color": FACILITY_COLOR_EXPR,
      "text-halo-color": "#05080c",
      "text-halo-width": 1.2,
    },
  });

  // ── thermal detections: a fire heatmap at planet scale, crisp points up close ──
  map.addSource("thermal", { type: "geojson", data: EMPTY_FC });
  map.addLayer({
    id: "thermal-heat",
    type: "heatmap",
    source: "thermal",
    maxzoom: 9,
    paint: {
      "heatmap-weight": ["interpolate", ["linear"], ["get", "risk"], 0, 0.05, 50, 0.3, 100, 1],
      "heatmap-intensity": ["interpolate", ["linear"], ["zoom"], 1, 0.35, 4, 0.7, 7, 1.3],
      "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 1, 4, 3, 7, 5, 13, 7, 22],
      "heatmap-color": HEAT_RAMP,
      "heatmap-opacity": ["interpolate", ["linear"], ["zoom"], 3, 0.9, 7.5, 0],
    },
  });
  map.addLayer({
    id: "thermal-glow",
    type: "circle",
    source: "thermal",
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 3, 6, 9, 11, 18],
      "circle-color": colorExpr(colorBy),
      "circle-blur": 1,
      // no per-point haze at planet scale — the heatmap carries that view
      "circle-opacity": ["interpolate", ["linear"], ["zoom"], 3.5, 0, 6, 0.35],
    },
  });
  map.addLayer({
    id: "thermal",
    type: "circle",
    source: "thermal",
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 2, 1.1, 6, 3.2, 11, 7],
      "circle-color": colorExpr(colorBy),
      "circle-opacity": ["interpolate", ["linear"], ["zoom"], 2, 0.75, 5, 1],
      "circle-stroke-color": "#05080c",
      "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 4, 0, 7, 0.8],
    },
  });
  map.addLayer({
    id: "thermal-selected",
    type: "circle",
    source: "thermal",
    filter: ["==", ["get", "id"], ""],
    paint: {
      "circle-radius": 11,
      "circle-color": "rgba(0,0,0,0)",
      "circle-stroke-color": "#ffffff",
      "circle-stroke-width": 1.8,
    },
  });

  // ── fire satellites ──
  map.addSource("sat-tracks", { type: "geojson", data: EMPTY_FC });
  map.addLayer({
    id: "sat-track-past",
    type: "line",
    source: "sat-tracks",
    filter: ["==", ["get", "part"], "past"],
    paint: {
      "line-color": ["get", "color"],
      "line-width": 1,
      "line-opacity": 0.3,
      "line-dasharray": [1, 2],
    },
  });
  map.addLayer({
    id: "sat-track-ahead",
    type: "line",
    source: "sat-tracks",
    filter: ["==", ["get", "part"], "ahead"],
    paint: { "line-color": ["get", "color"], "line-width": 1.4, "line-opacity": 0.8 },
  });
  map.addSource("sat-swath-fill", { type: "geojson", data: EMPTY_FC });
  map.addLayer({
    id: "sat-swath-fill",
    type: "fill",
    source: "sat-swath-fill",
    layout: { visibility: "none" },
    paint: { "fill-color": ["get", "color"], "fill-opacity": 0.08 },
  });
  map.addSource("sat-swath-line", { type: "geojson", data: EMPTY_FC });
  map.addLayer({
    id: "sat-swath-line",
    type: "line",
    source: "sat-swath-line",
    layout: { visibility: "none" },
    paint: { "line-color": ["get", "color"], "line-width": 1, "line-opacity": 0.6 },
  });
  map.addSource("sat-points", { type: "geojson", data: EMPTY_FC });
  map.addLayer({
    id: "sat-glow",
    type: "circle",
    source: "sat-points",
    paint: {
      "circle-radius": 12,
      "circle-color": ["get", "color"],
      "circle-blur": 1,
      "circle-opacity": 0.6,
    },
  });
  map.addLayer({
    id: "sat-core",
    type: "circle",
    source: "sat-points",
    paint: {
      "circle-radius": 3.2,
      "circle-color": "#ffffff",
      "circle-stroke-color": ["get", "color"],
      "circle-stroke-width": 2,
    },
  });
}

function satLabel(sat: FireSat): HTMLElement {
  const el = document.createElement("div");
  el.className = "sat-label";
  el.style.setProperty("--sat", sat.color);
  el.innerHTML = `<span class="sat-label-dot"></span>${esc(sat.name)}<span class="sat-label-inst">${sat.instrument}</span>`;
  return el;
}

export function GlobeMap(props: GlobeMapProps) {
  const { events, selectedId, colorBy, spin, layers, sats, quakes, naturalEvents, selectedHazard } =
    props;
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MLMap | null>(null);
  const [ready, setReady] = useState(false);
  // Latest props for map event handlers registered once at creation.
  const latest = useRef(props);
  latest.current = props;
  const borderLayers = useRef<string[]>([]);

  // ── create the map once ──
  useEffect(() => {
    if (!container.current) return;
    const map = new MLMap({
      container: container.current,
      style: DARK_STYLE,
      center: START_CENTER,
      zoom: fitZoom(container.current),
      minZoom: 1,
      maxZoom: 18,
      maxPitch: 60,
      attributionControl: { compact: true },
      canvasContextAttributes: { antialias: true },
    });
    mapRef.current = map;

    map.on("style.load", () => {
      map.setProjection({ type: "globe" });
      map.setSky({
        "sky-color": "#02060d",
        "horizon-color": "#0c2d4a",
        "fog-color": "#02060d",
        "sky-horizon-blend": 0.6,
        "horizon-fog-blend": 0.5,
        "fog-ground-blend": 0.9,
        "atmosphere-blend": ["interpolate", ["linear"], ["zoom"], 0, 1, 5, 1, 7, 0],
      });
      borderLayers.current = map
        .getStyle()
        .layers.filter((l) => l.id.startsWith("boundary_"))
        .map((l) => l.id);
      installLayers(map, latest.current.colorBy);
      setReady(true);
    });

    // hover tooltip + pointer cursor
    const tip = new Popup({
      closeButton: false,
      closeOnClick: false,
      offset: 12,
      className: "globe-tip",
    });
    const pick = (point: { x: number; y: number }): MapGeoJSONFeature | undefined => {
      const layersPresent = INTERACTIVE.filter(
        (id) => map.getLayer(id) && map.getLayoutProperty(id, "visibility") !== "none",
      );
      if (!layersPresent.length) return undefined;
      const hits = map.queryRenderedFeatures(
        [
          [point.x - 7, point.y - 7],
          [point.x + 7, point.y + 7],
        ],
        { layers: layersPresent },
      );
      // queryRenderedFeatures returns topmost first — satellites, then hotspots
      return hits[0];
    };
    const describe = (f: MapGeoJSONFeature): string | null => {
      const id = String(f.properties["id"]);
      const p = latest.current;
      if (f.layer.id === "thermal") {
        const e = p.events.find((x) => x.id === id);
        if (!e) return null;
        const why = e.facility
          ? `${e.facility.distanceKm.toFixed(1)} km from ${esc(e.facility.name || "unnamed site")} (${esc(e.facility.kind)})`
          : e.reasons?.length
            ? "no mapped facility within 3 km"
            : "";
        const seen = e.evidence ? ` · seen ${e.evidence.days} d` : "";
        return (
          `<b>${esc(e.id)}</b> · risk ${e.riskScore}<br>${esc(e.region)}<br>` +
          `<span>${esc(e.category)} · FRP ${e.frp.toFixed(1)} MW${seen}</span>` +
          (why ? `<br><span>${why}</span>` : "")
        );
      }
      if (f.layer.id === "facilities") {
        const props = f.properties as {
          name?: string;
          kind?: string;
          source?: string;
          capacityMw?: number;
        };
        const cap = props.capacityMw
          ? `${Math.round(props.capacityMw).toLocaleString()} MW · `
          : "";
        return `<b>${esc(props.name || "Unnamed site")}</b><br><span>${cap}${esc(props.kind ?? "")} · ${esc(props.source ?? "")}</span>`;
      }
      if (f.layer.id === "sat-core") {
        const s = p.sats.find((x) => x.id === id);
        return s
          ? `<b>${esc(s.name)}</b> · ${s.instrument}<br><span>FIRMS fire sensor · live position</span>`
          : null;
      }
      const h = [...p.quakes, ...p.naturalEvents].find((x) => x.id === id);
      if (!h) return null;
      return h.kind === "earthquake"
        ? `<b>M${h.magnitude?.toFixed(1) ?? "?"}</b> ${esc(h.title)}<br><span>${fmtAgo(h.time)} · USGS</span>`
        : `<b>${esc(h.categoryLabel)}</b> ${esc(h.title)}<br><span>${fmtAgo(h.time)} · NASA EONET</span>`;
    };

    map.on("mousemove", (e) => {
      cursorStore.set({
        lat: Math.round(e.lngLat.lat * 100) / 100,
        lon: Math.round(e.lngLat.lng * 100) / 100,
      });
      const f = pick(e.point);
      const html = f && describe(f);
      map.getCanvas().style.cursor = html ? "pointer" : "";
      if (html) tip.setLngLat(e.lngLat).setHTML(html).addTo(map);
      else tip.remove();
    });
    map.getCanvas().addEventListener("mouseleave", () => {
      cursorStore.set(null);
      tip.remove();
    });

    map.on("click", (e) => {
      const f = pick(e.point);
      if (!f) return;
      const id = String(f.properties["id"]);
      const p = latest.current;
      if (f.layer.id === "thermal") p.onSelect(id);
      else if (f.layer.id === "quakes" || f.layer.id === "eonet") {
        const h = [...p.quakes, ...p.naturalEvents].find((x) => x.id === id);
        if (h) p.onSelectHazard(h);
      }
    });

    // any direct manipulation stops the auto-rotation
    const stopSpin = () => latest.current.onInteract();
    map.on("mousedown", stopSpin);
    map.on("touchstart", stopSpin);
    map.on("wheel", stopSpin);

    return () => {
      tip.remove();
      map.remove();
      mapRef.current = null;
      setReady(false);
      cursorStore.set(null);
    };
  }, []);

  // ── data ──
  useEffect(() => {
    const map = mapRef.current;
    if (ready && map) setData(map, "thermal", eventsToGeoJSON(events));
  }, [ready, events]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    map.setPaintProperty("thermal", "circle-color", colorExpr(colorBy));
    map.setPaintProperty("thermal-glow", "circle-color", colorExpr(colorBy));
  }, [ready, colorBy]);

  useEffect(() => {
    const map = mapRef.current;
    if (ready && map) setData(map, "quakes", hazardsGeoJSON(quakes));
  }, [ready, quakes]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    setData(map, "eonet", hazardsGeoJSON(naturalEvents));
    setData(map, "eonet-tracks", stormTracksGeoJSON(naturalEvents));
  }, [ready, naturalEvents]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    setData(
      map,
      "hazard-selected",
      selectedHazard
        ? {
            type: "Feature",
            geometry: { type: "Point", coordinates: [selectedHazard.lon, selectedHazard.lat] },
            properties: {},
          }
        : EMPTY_FC,
    );
  }, [ready, selectedHazard]);

  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    map.setFilter("thermal-selected", ["==", ["get", "id"], selectedId ?? ""]);
    const e = selectedId ? latest.current.events.find((x) => x.id === selectedId) : undefined;
    if (e) {
      map.flyTo({
        center: [e.longitude, e.latitude],
        zoom: Math.max(map.getZoom(), 6),
        speed: 1.4,
        essential: true,
      });
    }
  }, [ready, selectedId]);

  // ── layer visibility ──
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    const shown: Record<string, boolean> = {};
    for (const [key, ids] of Object.entries(LAYER_IDS) as [keyof typeof LAYER_IDS, string[]][]) {
      let on = layers[key];
      if (key === "swath") on = layers.sats && layers.swath;
      for (const id of ids) shown[id] = on;
    }
    for (const id of borderLayers.current) shown[id] = layers.borders;
    for (const [id, on] of Object.entries(shown)) {
      if (map.getLayer(id)) map.setLayoutProperty(id, "visibility", on ? "visible" : "none");
    }
    // Imagery is for inspecting a site: a full-strength night shade would hide it.
    map.setPaintProperty("night", "raster-opacity", layers.imagery ? 0.35 : 1);
  }, [ready, layers]);

  // ── day / night, repainted every minute ──
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !layers.daynight) return;
    const canvas = document.createElement("canvas");
    const paint = () =>
      (map.getSource("night") as ImageSource | undefined)?.updateImage({
        image: paintNight(canvas, new Date()),
        coordinates: NIGHT_COORDS,
      });
    paint();
    const iv = window.setInterval(paint, 60_000);
    return () => window.clearInterval(iv);
  }, [ready, layers.daynight]);

  // ── satellites: positions every second, ground tracks every 30 s ──
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map || !layers.sats || !sats.length) {
      if (map && ready) {
        for (const id of ["sat-points", "sat-tracks", "sat-swath-fill", "sat-swath-line"]) {
          setData(map, id, EMPTY_FC);
        }
      }
      return;
    }
    const markers = new Map(
      sats.map((s) => [
        s.id,
        new Marker({
          element: satLabel(s),
          anchor: "left",
          offset: [10, 0],
          opacityWhenCovered: 0,
        }),
      ]),
    );
    const added = new Set<string>();
    let lastTracks = 0;
    const tick = () => {
      const now = new Date();
      const live = satPositions(sats, now);
      setData(map, "sat-points", satPointsGeoJSON(live));
      const swath = swathGeoJSON(live);
      setData(map, "sat-swath-fill", swath.fill);
      setData(map, "sat-swath-line", swath.outline);
      for (const s of live) {
        const m = markers.get(s.sat.id);
        if (!m) continue;
        m.setLngLat([s.lon, s.lat]);
        if (!added.has(s.sat.id)) {
          m.addTo(map);
          added.add(s.sat.id);
        }
      }
      if (now.getTime() - lastTracks > 30_000) {
        lastTracks = now.getTime();
        setData(map, "sat-tracks", satTracksGeoJSON(sats, now));
      }
    };
    tick();
    const iv = window.setInterval(tick, 1000);
    return () => {
      window.clearInterval(iv);
      markers.forEach((m) => m.remove());
    };
  }, [ready, sats, layers.sats]);

  // ── animation loop: auto-rotate, the recent-quake pulse, the selection pulse ──
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    let raf = 0;
    let last = performance.now();
    const frame = (t: number) => {
      const dt = Math.min(0.1, (t - last) / 1000);
      last = t;
      if (spin && map.getZoom() < 5 && !map.isMoving()) {
        const c = map.getCenter();
        map.setCenter([c.lng + dt * SPIN_DEG_PER_SEC, c.lat]);
      }
      if (layers.quakes) {
        const f = ((t / 1000) % 1.6) / 1.6;
        map.setPaintProperty("quake-pulse", "circle-radius", 6 + f * 16);
        map.setPaintProperty("quake-pulse", "circle-stroke-opacity", 0.55 * (1 - f));
      }
      if (selectedId) {
        map.setPaintProperty("thermal-selected", "circle-radius", 10 + Math.sin(t / 220) * 2.5);
      }
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [ready, spin, layers.quakes, selectedId]);

  // MapLibre's stylesheet forces `position: relative` on the map element, so the
  // positioning lives on a wrapper and the map just fills it.
  return (
    <div className="globe-map absolute inset-0">
      <div ref={container} className="h-full w-full" />
    </div>
  );
}
