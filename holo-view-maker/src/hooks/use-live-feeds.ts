import { useEffect, useState } from "react";
import type { FeedState } from "@/lib/layers";
import { loadFireSats, type FireSatSet } from "@/lib/satellites";

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

/** Polls a keyless public feed. Keeps showing the last good data (and says so)
 * when a refresh fails, rather than blanking the layer. */
export function usePolledFeed<T>(
  fetcher: () => Promise<T[]>,
  intervalMs: number,
): { data: T[]; feed: FeedState } {
  const [data, setData] = useState<T[]>([]);
  const [feed, setFeed] = useState<FeedState>({ status: "loading", count: 0, updatedAt: null });

  useEffect(() => {
    let alive = true;
    const run = async () => {
      try {
        const next = await fetcher();
        if (!alive) return;
        setData(next);
        setFeed({ status: "ok", count: next.length, updatedAt: Date.now() });
      } catch (err) {
        if (!alive) return;
        setFeed((prev) =>
          prev.updatedAt
            ? {
                ...prev,
                status: "fallback",
                note: `refresh failed, showing the last data (${errorMessage(err)})`,
              }
            : { status: "error", count: 0, updatedAt: null, note: errorMessage(err) },
        );
      }
    };
    run();
    const iv = window.setInterval(run, intervalMs);
    return () => {
      alive = false;
      window.clearInterval(iv);
    };
  }, [fetcher, intervalMs]);

  return { data, feed };
}

/** Orbital elements for the FIRMS satellites, reloaded every 6 hours. */
export function useFireSats(): { set: FireSatSet | null; feed: FeedState } {
  const [set, setSet] = useState<FireSatSet | null>(null);
  const [feed, setFeed] = useState<FeedState>({ status: "loading", count: 0, updatedAt: null });

  useEffect(() => {
    let alive = true;
    const run = () =>
      loadFireSats()
        .then((next) => {
          if (!alive) return;
          setSet(next);
          const ageH = (Date.now() - next.fetchedAt) / 3600_000;
          setFeed({
            status: next.source === "bundled" ? "fallback" : "ok",
            count: next.sats.length,
            updatedAt: next.fetchedAt,
            note:
              next.source === "live"
                ? "CelesTrak · live elements"
                : next.source === "cache"
                  ? `CelesTrak · cached ${ageH < 1 ? "<1" : ageH.toFixed(0)} h ago`
                  : `offline snapshot · ${ageH < 24 ? `${ageH.toFixed(0)} h` : `${(ageH / 24).toFixed(0)} d`} old`,
          });
        })
        .catch((err) => {
          if (alive)
            setFeed({ status: "error", count: 0, updatedAt: null, note: errorMessage(err) });
        });
    run();
    const iv = window.setInterval(run, 6 * 3600_000);
    return () => {
      alive = false;
      window.clearInterval(iv);
    };
  }, []);

  return { set, feed };
}

/** Re-renders on an interval — for clocks and "in 42 min" countdowns. */
export function useNow(intervalMs: number): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const iv = window.setInterval(() => setNow(new Date()), intervalMs);
    return () => window.clearInterval(iv);
  }, [intervalMs]);
  return now;
}
