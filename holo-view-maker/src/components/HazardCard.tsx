import { X } from "lucide-react";
import { EONET_COLORS, type Hazard } from "@/lib/hazards";
import { fmtAgo, fmtIst, fmtUtc } from "@/lib/format";

/** The selected open natural event, pinned over the globe. Context for the
 *  thermal layer, so it stays small and never covers the detection panel. */
export function HazardCard({ hazard, onClose }: { hazard: Hazard; onClose: () => void }) {
  const color = EONET_COLORS[hazard.category] ?? "#a1adba";
  const when = new Date(hazard.time);

  return (
    <div className="panel absolute top-3 left-3 z-20 w-[19rem] max-w-[calc(100%-1.5rem)] p-3">
      <div className="flex items-start gap-2">
        <span className="mt-1 size-2.5 shrink-0 rounded-[2px]" style={{ background: color }} />
        <div className="min-w-0 flex-1">
          <p className="text-[0.72rem] text-muted-foreground">{hazard.categoryLabel}, NASA EONET</p>
          <p className="text-[0.86rem] leading-snug font-medium">{hazard.title}</p>
        </div>
        <button
          onClick={onClose}
          aria-label="Close"
          className="text-muted-foreground transition-colors duration-150 hover:text-foreground"
        >
          <X className="size-3.5" />
        </button>
      </div>

      <dl className="mt-2 flex flex-col gap-1 text-[0.72rem]">
        <div className="flex justify-between gap-3">
          <dt className="text-muted-foreground">Observed</dt>
          <dd className="font-mono tabular-nums">
            {fmtUtc(when)} UTC, {fmtIst(when)} IST
          </dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-muted-foreground">Age</dt>
          <dd>{fmtAgo(hazard.time)}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-muted-foreground">Position</dt>
          <dd className="font-mono tabular-nums">
            {hazard.lat.toFixed(2)}, {hazard.lon.toFixed(2)}
          </dd>
        </div>
      </dl>

      {hazard.url && (
        <a
          href={hazard.url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-2 inline-block text-[0.72rem] text-primary transition-colors duration-150 hover:underline"
        >
          Open the source record
        </a>
      )}
    </div>
  );
}
