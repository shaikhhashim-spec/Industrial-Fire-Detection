// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - TanStack devtools (dev-only, first), tanstackStart, viteReact, tailwindcss, tsConfigPaths,
//     nitro (build-only using cloudflare as a default target), VITE_* env injection, @ path alias,
//     React/TanStack dedupe, error logger plugins, and sandbox detection (port/host/strictPort).
// You can pass additional config via defineConfig({ vite: { ... }, etc... }) if needed.
import { defineConfig } from "@lovable.dev/vite-tanstack-config";
import type { Plugin } from "vite";

/**
 * The dev-only devtools plugin injects `data-tsd-source="..."` on every JSX element.
 * react-three-fiber tries to apply that as a Three.js property and throws
 * `R3F: Cannot set "data-tsd-source"`. Strip it from our three.js component files.
 */
function stripSourceTagsFromThreeFiles(): Plugin {
  return {
    name: "strip-tsd-source-in-three-components",
    enforce: "post",
    apply: "serve",
    transform(code, id) {
      if (!/src\/components\/globe\//.test(id)) return null;
      if (!code.includes("data-tsd-source")) return null;
      return {
        code: code.replace(/\s*"data-tsd-source":\s*"[^"]*",?/g, "").replace(
          /\sdata-tsd-source="[^"]*"/g,
          "",
        ),
        map: null,
      };
    },
  };
}

export default defineConfig({
  tanstackStart: {
    server: {
      entry: "server",
    },
    prerender: {
      enabled: true,
      autoSubfolderIndex: true,
      autoStaticPathsDiscovery: true,
      crawlLinks: true,
    },
  },
  vite: {
    base: "/SIH26162/",
    plugins: [stripSourceTagsFromThreeFiles()],
  },
});