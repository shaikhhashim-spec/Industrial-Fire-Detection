/**
 * Resolve a file in `public/` to a URL that works wherever the app is hosted.
 *
 * The site is served from the domain root in development but from a
 * subpath on GitHub Pages (`/<repo>/`), so a bare `/data/x.json` would
 * 404 there. Vite exposes the deploy base as `import.meta.env.BASE_URL`.
 */
export function assetUrl(path: string): string {
  return `${import.meta.env.BASE_URL}${path.replace(/^\/+/, "")}`;
}

/**
 * The page above the one the app is served from, or null at the site root. The
 * globe is served under /globe/ both locally (beside the dashboard) and on the
 * public site (beside its Overview), so its parent is the way back to either.
 */
export function parentPath(base: string = import.meta.env.BASE_URL): string | null {
  if (base === "/") return null;
  return base.replace(/[^/]+\/$/, "");
}
