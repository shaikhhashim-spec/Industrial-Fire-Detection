/* Settings here is read-only static configuration (see settings.html); this
 * page only needs the shared nav and the topbar's live-data freshness line. */
import { mountNav } from "./nav.mjs";
import { loadData, renderMeta } from "./page.mjs";

mountNav("settings.html");

loadData()
  .then((data) => renderMeta(data.meta ?? {}))
  .catch((err) => console.warn("Could not read the live data:", err));
