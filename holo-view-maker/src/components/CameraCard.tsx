import { useMemo } from "react";
import { X } from "lucide-react";
import { CAMERA_COLORS, compass, describeCamera, type Camera } from "@/lib/cameras";
import { distanceKm } from "@/lib/hazards";
import { RISK_COLORS, type ThermalEvent } from "@/lib/thermal";

const NEARBY_KM = 5;

/** The selected camera, pinned over the globe. It answers the question that
 *  matters for a fire: what is detected near this camera, and is anyone able to
 *  look. It says plainly that the layer is locations only. */
export function CameraCard({
  camera,
  events,
  onClose,
  onSelectEvent,
}: {
  camera: Camera;
  events: ThermalEvent[];
  onClose: () => void;
  onSelectEvent: (id: string) => void;
}) {
  const near = useMemo(
    () =>
      events
        .map((event) => ({
          event,
          km: distanceKm(camera.lat, camera.lon, event.latitude, event.longitude),
        }))
        .filter((x) => x.km <= NEARBY_KM)
        .sort((a, b) => a.km - b.km),
    [camera, events],
  );

  return (
    <div className="panel absolute top-3 left-3 z-20 w-[19rem] max-w-[calc(100%-1.5rem)] p-3">
      <div className="flex items-start gap-2">
        <span
          className="mt-1 size-2.5 shrink-0 rounded-[2px]"
          style={{ background: CAMERA_COLORS[camera.kind] }}
        />
        <div className="min-w-0 flex-1">
          <p className="text-[0.72rem] text-muted-foreground">
            {camera.plateReader ? "Plate reader camera" : "Mapped camera"}, OpenStreetMap
          </p>
          <p className="text-[0.86rem] leading-snug font-medium">
            {camera.name || `${camera.kind} camera`}
          </p>
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
          <dt className="text-muted-foreground">Watches</dt>
          <dd>{camera.kind}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-muted-foreground">Camera</dt>
          <dd className="first-letter:uppercase">{describeCamera(camera)}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-muted-foreground">Faces</dt>
          <dd className="font-mono tabular-nums">
            {camera.heading != null
              ? `${compass(camera.heading)}, ${Math.round(camera.heading)}°`
              : "not mapped"}
          </dd>
        </div>
        {camera.operator && (
          <div className="flex justify-between gap-3">
            <dt className="text-muted-foreground">Operator</dt>
            <dd className="truncate">{camera.operator}</dd>
          </div>
        )}
        <div className="flex justify-between gap-3">
          <dt className="text-muted-foreground">State</dt>
          <dd>{camera.state}</dd>
        </div>
        <div className="flex justify-between gap-3">
          <dt className="text-muted-foreground">Position</dt>
          <dd className="font-mono tabular-nums">
            {camera.lat.toFixed(4)}, {camera.lon.toFixed(4)}
          </dd>
        </div>
      </dl>

      <div className="mt-3 border-t border-border pt-2">
        <span className="field-label">Detections within {NEARBY_KM} km</span>
        {near.length === 0 ? (
          <p className="mt-1 text-[0.72rem] text-muted-foreground">None in the loaded window.</p>
        ) : (
          <div className="mt-1 flex flex-col">
            {near.slice(0, 3).map(({ event, km }) => (
              <button
                key={event.id}
                onClick={() => onSelectEvent(event.id)}
                className="flex items-center gap-2 rounded-sm py-1 text-left text-[0.72rem] transition-colors duration-150 hover:bg-muted"
              >
                <span
                  className="size-2 shrink-0 rounded-[2px]"
                  style={{ background: RISK_COLORS[event.riskLevel] }}
                />
                <span className="font-mono text-[0.66rem] text-muted-foreground">{event.id}</span>
                <span className="truncate">{event.region}</span>
                <span className="ml-auto font-mono tabular-nums text-muted-foreground">
                  {km.toFixed(1)} km
                </span>
              </button>
            ))}
            {near.length > 3 && (
              <p className="mt-0.5 text-[0.66rem] text-muted-foreground">
                and {near.length - 3} more
              </p>
            )}
          </div>
        )}
      </div>

      <p className="mt-2 text-[0.66rem] leading-snug text-muted-foreground">
        A location mapped by OpenStreetMap volunteers. This site has no video from it.
      </p>
      <a
        href={`https://www.openstreetmap.org/node/${camera.id}`}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-1.5 inline-block text-[0.72rem] text-primary transition-colors duration-150 hover:underline"
      >
        Open the OpenStreetMap record
      </a>
    </div>
  );
}
