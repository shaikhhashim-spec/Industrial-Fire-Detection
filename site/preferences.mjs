import { REGIONS } from "./regions.mjs";

export const PREFERENCES_KEY = "thermal-workspace-preferences-v1";
export const DEFAULT_PREFERENCES = { region: "global", pageSize: 100, autoReload: false };

export function normalizePreferences(value) {
  return { region: REGIONS.some((region) => region.id === value?.region) ? value.region : "global",
    pageSize: [50, 100, 250].includes(value?.pageSize) ? value.pageSize : 100,
    autoReload: value?.autoReload === true };
}

export function readPreferences(storage) {
  try { return normalizePreferences(JSON.parse(storage?.getItem(PREFERENCES_KEY) ?? "null")); }
  catch { return { ...DEFAULT_PREFERENCES }; }
}

export function browserPreferences() {
  try { return readPreferences(globalThis.localStorage); }
  catch { return { ...DEFAULT_PREFERENCES }; }
}

export function savePreferences(storage, value) {
  const preferences = normalizePreferences(value);
  try {
    if (!storage) throw new Error("Storage unavailable");
    storage.setItem(PREFERENCES_KEY, JSON.stringify(preferences));
    return { ok: true, preferences };
  } catch { return { ok: false, preferences }; }
}
