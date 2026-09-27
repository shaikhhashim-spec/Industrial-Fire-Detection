const SVG_NS = "http://www.w3.org/2000/svg";
// document.createElement("path") makes a plain, invisible HTMLUnknownElement —
// SVG tags need createElementNS or the icon never paints, with no console error.
const SVG_TAGS = new Set(["svg", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "g"]);

/** Tiny DOM builder shared by every page of the public site. No framework: this
 * is the one place that turns `{ class, onclick, ... }` into real DOM. */
export function h(tag, attrs = {}, ...children) {
  const el = SVG_TAGS.has(tag) ? document.createElementNS(SVG_NS, tag) : document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value == null || value === false) continue;
    if (key === "class") el.setAttribute("class", value);
    else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else el.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    el.append(typeof child === "object" ? child : document.createTextNode(String(child)));
  }
  return el;
}

export const num = (n) => n.toLocaleString("en-US");
