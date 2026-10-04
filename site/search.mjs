/** Literal words may match different fields; accents and repeated spaces are ignored. */
export function matchesSearch(values, query) {
  const normalize = (value) => String(value ?? "").normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
  const terms = normalize(query).trim().split(/\s+/).filter(Boolean);
  const text = values.map(normalize).join(" ");
  return terms.every((term) => text.includes(term));
}
