/*
 * Recovering from a deploy that happened while a page was cached.
 *
 * Every build renames its script files, and GitHub Pages lets a browser reuse
 * the page for ten minutes. A browser holding the previous page can therefore
 * ask for a script that no longer exists, and the app dies with "This page
 * didn't load". One reload fetches the current page and its current files.
 * The timestamp stops a genuinely broken deploy from reloading forever.
 */
const KEY = "ti-stale-reload";
const MIN_GAP_MS = 30_000;

/** Reload once for a new deploy. False when it already did within the last half
 * minute, or when the browser will not let it remember that (a loop is worse). */
export function reloadOnceForNewDeploy(): boolean {
  try {
    const last = Number(window.sessionStorage.getItem(KEY) ?? 0);
    if (Date.now() - last < MIN_GAP_MS) return false;
    window.sessionStorage.setItem(KEY, String(Date.now()));
  } catch {
    return false;
  }
  window.location.reload();
  return true;
}

/** Whether an error is a script or style file that could not be loaded. */
export function isFileLoadError(error: unknown): boolean {
  const text = error instanceof Error ? `${error.name} ${error.message}` : String(error);
  return /dynamically imported module|Importing a module script failed|Loading (CSS )?chunk|Unable to preload|error loading dynamically/i.test(
    text,
  );
}

/** Runs from the page itself, before any app file, for the case where the app's
 * own first script is the one that is gone and nothing else can react. */
export const STALE_RELOAD_SCRIPT = `window.addEventListener("error",function(e){var t=e.target;if(!t||t.tagName!=="SCRIPT"||!t.src||t.src.indexOf("/assets/")<0)return;try{var n=Date.now();if(n-Number(sessionStorage.getItem("${KEY}")||0)<${MIN_GAP_MS})return;sessionStorage.setItem("${KEY}",String(n));location.reload()}catch(_){}},true);`;

/** Reload when Vite reports that a lazily loaded file could not be fetched. The
 * event is left alone (not cancelled) so the real error still reaches the error
 * page if the reload does not help. */
export function watchForStaleDeploy(): void {
  window.addEventListener("vite:preloadError", () => {
    reloadOnceForNewDeploy();
  });
}
