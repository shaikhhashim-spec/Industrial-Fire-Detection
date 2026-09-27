/* Investigations is a local-only, belt-region feature (see the panel text in
 * investigations.html); this page only needs the shared nav and the topbar's
 * live-data freshness line. */
import { mountNav } from "./nav.mjs";
import { loadData, renderMeta } from "./page.mjs";

mountNav("investigations.html");

loadData()
  .then((data) => renderMeta(data.meta ?? {}))
  .catch((err) => console.warn("Could not read the live data:", err));
