# Thermal Intelligence — 3D Interactive Frontend

A 3D interactive command-center frontend for the uploaded Streamlit
"THERMAL INTELLIGENCE" dashboard (AI-assisted early warning and
prioritization of industrial fires and persistent thermal sources),
rebuilt as a React + Three.js application centered on a photorealistic
interactive globe.

## What Was Built

Everything created or modified for this project, file by file.

### Data & Domain Logic

#### `src/lib/thermal.ts`
The core domain module, preserved from the original Python dashboard:
- TypeScript types: `ThermalEvent`, `Category`, `RiskLevel`
- Color palette matching the original dashboard's risk/category colors
- Deterministic mock satellite detections across Indian industrial and
  thermal corridors (matching the original app's demo data)
- Risk scoring, persistence tracking, FRP (Fire Radiative Power),
  confidence, satellite, status, and historical trend fields
- `latLonToVector3()` — latitude/longitude to Three.js sphere-coordinate
  conversion used by every globe component

### 3D Globe Components

#### `src/components/globe/Earth.tsx`
The photorealistic Earth:
- Satellite day-map texture with terrain relief (bump mapping)
- Specular ocean shading
- City-lights night texture on the dark side
- Drifting cloud layer
- Sun-lit directional lighting
- Fresnel atmospheric limb glow

#### `src/components/globe/Coastlines.tsx`
- Fetches Natural Earth 110m land GeoJSON from `/geo/land-110m.geojson`
- Renders land outlines as spherical line geometry
- Draws the latitude/longitude graticule grid

#### `src/components/globe/Markers.tsx`
- Clickable, pulsing thermal-detection beams rising from the surface
- Beam height and color encode event risk level or category
  (toggleable from the UI)
- Selected events get a larger animated halo

#### `src/components/globe/ThermalGlobe.tsx`
The assembled scene:
- React Three Fiber `<Canvas>` with orbit and zoom controls
- Earth, coastlines, graticule, markers, starfield, and lighting
- Auto-rotation toggle
- Initial camera rotation aimed at the South Asian monitoring region

### UI Components

#### `src/components/EventDetail.tsx`
Full investigation record for the selected event:
- Event ID, region, status, category
- Risk score with progress bar and FRP sparkline
- Coordinates, brightness, confidence, persistence, detection count
- Satellite, overpass time, acquisition date
- The original dashboard's verification caveat

### Routes & App Shell

#### `src/routes/index.tsx`
The main dashboard route:
- Header metrics: active events, critical events, high-risk events,
  total FRP
- Interactive 3D globe
- Category/risk beam-color toggle, minimum-risk slider,
  auto-rotate checkbox
- Classification visibility filters and risk legend
- Clickable priority queue (clicking an event opens its detail panel)
- Responsive three-column desktop layout, stacked on mobile
- SEO title and description metadata

#### `src/routes/__root.tsx`
- Root layout with `<Outlet />`
- IBM Plex Sans / IBM Plex Mono font loading
- Sonner `<Toaster />` mount

### Styling & Types

#### `src/styles.css`
Dark orbital command-center design system:
- Semantic design tokens (no hardcoded colors in components)
- IBM Plex typography
- Panel styles, borders, muted blue accents
- Atmospheric radial background treatment

#### `src/three-fiber.d.ts`
Extends JSX intrinsic element typings so React Three Fiber elements
(`<mesh>`, `<sphereGeometry>`, etc.) type-check.

### Static Data

#### `public/geo/land-110m.geojson`
Natural Earth 110m land polygons, downloaded for coastline rendering
on the globe.

### Configuration

#### `vite.config.ts`
Adjusted to strip the dev-only `data-tsd-source` attributes a devtools
plugin was injecting into Three.js JSX elements, which caused the R3F
runtime error `Cannot set "data-tsd-source"` and a blank screen.

## Dependencies Added

- `three` — 3D engine
- `@react-three/fiber` — React renderer for Three.js
- `@react-three/drei` — helpers (OrbitControls, Stars, textures)
- `@types/three` — TypeScript types

## How to Run

The dev server starts automatically. Open the preview to see the
dashboard; drag to rotate the globe, scroll to zoom, click a beam or a
priority-queue entry to inspect an event.
