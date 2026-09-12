// MapLibre 6 runs tile and GeoJSON decoding in a module worker that imports a
// sibling "shared" module by relative URL. Vite's dependency pre-bundling breaks
// that relative import, so the map would draw nothing but raster layers.
// Self-host both files from the installed version and point MapLibre at them
// (see setWorkerUrl in src/components/map/GlobeMap.tsx). Approach from OSIRIS
// (github.com/simplifaisoul/osiris, MIT — tools/prepare-map-worker.mjs).
import { copyFile, mkdir, readdir, readFile, rm } from "node:fs/promises";

const root = new URL("../", import.meta.url);
const source = new URL("node_modules/maplibre-gl/", root);
const { version } = JSON.parse(await readFile(new URL("package.json", source), "utf8"));
const vendor = new URL("public/vendor/maplibre/", root);
const target = new URL(`${version}/`, vendor);

await mkdir(target, { recursive: true });
for (const file of ["dist/maplibre-gl-worker.mjs", "dist/maplibre-gl-shared.mjs", "LICENSE.txt"]) {
  await copyFile(new URL(file, source), new URL(file.split("/").at(-1), target));
}

// Keep only the installed version, so a stale copy can't mask a broken worker URL.
for (const entry of await readdir(vendor, { withFileTypes: true })) {
  if (entry.isDirectory() && entry.name !== version) {
    await rm(new URL(`${entry.name}/`, vendor), { recursive: true, force: true });
    console.log(`prepare-map-worker: pruned stale maplibre ${entry.name}`);
  }
}
console.log(`prepare-map-worker: maplibre ${version} worker ready`);
