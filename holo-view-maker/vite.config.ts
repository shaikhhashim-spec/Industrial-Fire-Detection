// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - TanStack devtools (dev-only, first), tanstackStart, viteReact, tailwindcss, tsConfigPaths,
//     nitro (build-only using cloudflare as a default target), VITE_* env injection, @ path alias,
//     React/TanStack dedupe, error logger plugins, and sandbox detection (port/host/strictPort).
// You can pass additional config via defineConfig({ vite: { ... }, etc... }) if needed.
import { defineConfig } from "@lovable.dev/vite-tanstack-config";

// GitHub Pages serves a project site from /<repo>/, and everywhere else (local dev)
// the app lives at the root. BASE_PATH overrides both: start_all.py builds with
// BASE_PATH=/globe/ for the gateway, which serves the globe under that path.
const repo = process.env["GITHUB_REPOSITORY"]?.split("/")[1];
const base =
  process.env["BASE_PATH"] ?? (process.env["GITHUB_ACTIONS"] && repo ? `/${repo}/` : "/");

export default defineConfig({
  tanstackStart: {
    // Redirect TanStack Start's bundled server entry to src/server.ts (our SSR error wrapper).
    server: { entry: "server" },
    // Pre-render to static HTML so GitHub Pages can serve the site.
    prerender: {
      enabled: true,
      autoSubfolderIndex: true,
      autoStaticPathsDiscovery: true,
      crawlLinks: true,
    },
  },
  vite: { base },
});
