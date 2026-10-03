/** Root deep links belong to the globe; an unscoped visit stays on Overview. */
export function globeRedirectTarget(href) {
  const source = new URL(href);
  if (!source.searchParams.has("region") && !source.searchParams.has("flat")) return null;

  const target = new URL("globe/", source);
  target.search = source.search;
  if (target.searchParams.has("flat")) target.searchParams.delete("flat");
  target.hash = source.hash;
  return target.href;
}

export function redirectRootToGlobe(location) {
  const target = globeRedirectTarget(location.href);
  if (!target) return false;
  location.replace(target);
  return true;
}
