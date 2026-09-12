import { useSyncExternalStore } from "react";

export interface Store<T> {
  get: () => T;
  set: (next: T) => void;
  subscribe: (listener: () => void) => () => void;
}

/** A tiny external store for values that change every frame (cursor position).
 * Keeping them out of React state means the dashboard route — and its thousands
 * of globe markers — never re-renders just because the mouse moved. */
export function createStore<T>(initial: T): Store<T> {
  let value = initial;
  const listeners = new Set<() => void>();
  return {
    get: () => value,
    set: (next) => {
      if (Object.is(next, value)) return;
      value = next;
      listeners.forEach((l) => l());
    },
    subscribe: (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

export function useStore<T>(store: Store<T>): T {
  return useSyncExternalStore(store.subscribe, store.get, store.get);
}

/** Lat/lon under the pointer on the globe, or null when off the sphere. */
export const cursorStore = createStore<{ lat: number; lon: number } | null>(null);
