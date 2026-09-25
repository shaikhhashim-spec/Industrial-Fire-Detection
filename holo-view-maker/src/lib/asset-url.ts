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
