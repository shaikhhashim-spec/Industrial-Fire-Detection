import { ExternalLink, X } from "lucide-react";
import type { Webcam } from "@/lib/webcams";

/** A live webcam from SkylineWebcams, pinned over the globe. The video plays on
 *  their site: they do not allow embedding, so this card only links out. */
export function WebcamCard({ webcam, onClose }: { webcam: Webcam; onClose: () => void }) {
  return (
    <div className="panel absolute top-3 left-3 z-20 w-[19rem] max-w-[calc(100%-1.5rem)] p-3">
      <div className="flex items-start gap-2">
        <span className="mt-1 size-2.5 shrink-0 rounded-[2px] bg-foreground" />
        <div className="min-w-0 flex-1">
          <p className="text-[0.72rem] text-muted-foreground">Live webcam, SkylineWebcams</p>
          <p className="text-[0.86rem] leading-snug font-medium">{webcam.name}</p>
        </div>
        <button
          onClick={onClose}
          aria-label="Close"
          className="text-muted-foreground transition-colors duration-150 hover:text-foreground"
        >
          <X className="size-3.5" />
        </button>
      </div>

      {webcam.about && <p className="mt-2 text-[0.72rem] leading-snug">{webcam.about}</p>}

      <dl className="mt-2 flex flex-col gap-1 text-[0.72rem]">
        <div className="flex justify-between gap-3">
          <dt className="text-muted-foreground">Place</dt>
          <dd>
            {webcam.town}, {webcam.state}
          </dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-muted-foreground">Marker</dt>
          <dd className="font-mono tabular-nums">
            {webcam.lat.toFixed(3)}, {webcam.lon.toFixed(3)}
          </dd>
        </div>
      </dl>

      <a
        href={webcam.url}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-3 inline-flex items-center gap-1.5 rounded-sm border border-border bg-muted px-2.5 py-1.5 text-[0.76rem] transition-colors duration-150 hover:bg-accent"
      >
        Watch live on SkylineWebcams
        <ExternalLink className="size-3.5" />
      </a>
      <p className="mt-2 text-[0.66rem] leading-snug text-muted-foreground">
        SkylineWebcams does not allow its video to be embedded, so it plays on their site. The
        marker is the town centre, not the camera.
      </p>
    </div>
  );
}
