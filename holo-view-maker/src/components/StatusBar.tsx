/*
 * Bottom status strip — feed health, next overpass, cursor position and clocks.
 * Pattern adapted from the OSIRIS global status bar
 * (github.com/simplifaisoul/osiris, MIT, © 2026 simplifaisoul).
 */
import { useMemo } from "react";
import { useNow } from "@/hooks/use-live-feeds";
import { cursorStore, useStore } from "@/lib/globe-store";
import { fmtIn, fmtIst, fmtLat, fmtLon, fmtUtc } from "@/lib/format";
import { STATUS_DOT, feedTitle, type FeedState, type FeedStatus } from "@/lib/layers";
import { DEFAULT_AOI, nextPasses, type FireSat } from "@/lib/satellites";

function Chip({
  label,
  status,
  value,
  title,
}: {
  label: string;
  status: FeedStatus;
  value: string;
  title: string;
}) {
  return (
    <span className="flex items-center gap-1.5" title={title}>
      <span className={`size-2 rounded-[2px] ${STATUS_DOT[status]}`} />
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono text-foreground/85 tabular-nums">{value}</span>
    </span>
  );
}

/** A public feed chip: the count once it answers, and what went wrong if not. */
function FeedChip({ label, feed }: { label: string; feed: FeedState }) {
  const shown =
    feed.status === "loading"
      ? "loading"
      : feed.status === "error"
        ? "down"
        : feed.count.toLocaleString();
  return (
    <Chip label={label} status={feed.status} value={shown} title={`${label}: ${feedTitle(feed)}`} />
  );
}

function NextPass({ sats }: { sats: FireSat[] }) {
  const now = useNow(30_000);
  const minute = Math.floor(now.getTime() / 60_000);
  const pass = useMemo(
    () =>
      sats.length
        ? nextPasses(sats, DEFAULT_AOI.lat, DEFAULT_AOI.lon, new Date(minute * 60_000), 24)[0]
        : undefined,
    [sats, minute],
  );
  if (!pass) return null;
  const inWhen = fmtIn(pass.time, now);
  return (
    <span
      className="flex items-center gap-1.5"
      title={`Next time ${DEFAULT_AOI.name} falls inside a FIRMS sensor swath (closest approach ${Math.round(pass.offNadirKm)} km from nadir)`}
    >
      <span className="text-muted-foreground">Next pass</span>
      <span className="size-2 rounded-[2px]" style={{ background: pass.sat.color }} />
      <span className="text-foreground/85">
        {pass.sat.name} {pass.sat.instrument} over {DEFAULT_AOI.name}
      </span>
      <span className="font-mono text-foreground/85 tabular-nums">
        {inWhen === "now" ? "overhead now" : `${fmtUtc(pass.time)} UTC, ${inWhen}`}
      </span>
      <span className="text-muted-foreground">
        {pass.daylight ? "daylight pass" : "night pass"}
      </span>
    </span>
  );
}

function CursorReadout() {
  const c = useStore(cursorStore);
  return (
    <span className="w-[9.5rem] text-right font-mono tabular-nums text-foreground/85">
      {c ? (
        `${fmtLat(c.lat)} ${fmtLon(c.lon)}`
      ) : (
        <span className="font-sans text-muted-foreground">cursor off globe</span>
      )}
    </span>
  );
}

function Clocks() {
  const now = useNow(1000);
  return (
    <>
      <span className="font-mono tabular-nums">
        <span className="font-sans text-muted-foreground">UTC </span>
        {fmtUtc(now, true)}
      </span>
      <span className="font-mono tabular-nums">
        <span className="font-sans text-muted-foreground">IST </span>
        {fmtIst(now, true)}
      </span>
    </>
  );
}

export interface StatusBarProps {
  pipeline: { mode: "live" | "none"; count: number; loading: boolean };
  usgs: FeedState;
  eonet: FeedState;
  tle: FeedState;
  sats: FireSat[];
  onShowHelp: () => void;
}

export function StatusBar({ pipeline, usgs, eonet, tle, sats, onShowHelp }: StatusBarProps) {
  return (
    <footer className="-mx-4 mt-3 flex h-8 shrink-0 items-center gap-x-5 overflow-x-auto border-t border-border bg-card px-4 text-[0.68rem] whitespace-nowrap">
      <Chip
        label="Pipeline"
        status={pipeline.loading ? "loading" : pipeline.mode === "live" ? "ok" : "error"}
        value={
          pipeline.mode === "live" ? `live, ${pipeline.count.toLocaleString()} events` : "no export"
        }
        title={
          pipeline.mode === "live"
            ? "Live NASA FIRMS detections inside India (/data/events.json)"
            : "No live pipeline export found. Run the pipeline from the dashboard."
        }
      />
      <FeedChip label="Quakes" feed={usgs} />
      <FeedChip label="Events" feed={eonet} />
      <Chip
        label="Orbits"
        status={tle.status}
        value={
          tle.status === "loading"
            ? "loading"
            : tle.status === "error"
              ? "down"
              : (tle.note ?? "current")
        }
        title={`Orbital elements: ${feedTitle(tle)}`}
      />
      <span className="h-3 w-px bg-border" />
      <NextPass sats={sats} />
      <span className="ml-auto" />
      <CursorReadout />
      <Clocks />
      <button onClick={onShowHelp} title="Keyboard shortcuts" className="kbd transition-colors duration-150 hover:text-foreground">
        ?
      </button>
    </footer>
  );
}
