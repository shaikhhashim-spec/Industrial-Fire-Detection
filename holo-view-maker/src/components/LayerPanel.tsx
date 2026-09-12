/*
 * Grouped layer toggles with live counts and feed health — layout adapted from
 * the OSIRIS layer panel (github.com/simplifaisoul/osiris, MIT, © 2026
 * simplifaisoul). See THIRD_PARTY_NOTICES.md.
 */
import type { ReactNode } from "react";
import {
  LAYER_GROUPS,
  STATUS_DOT,
  feedTitle,
  type FeedState,
  type LayerKey,
  type Layers,
} from "@/lib/layers";
import { FACILITY_COLORS, FACILITY_LEGEND } from "@/lib/facilities";
import { EONET_COLORS, QUAKE_COLOR } from "@/lib/hazards";
import type { FireSat } from "@/lib/satellites";

/** Presentational only — the whole row is the button (a button inside a
 * button is invalid HTML and silently drops the inner click). */
function Switch({ on }: { on: boolean }) {
  return (
    <span
      role="presentation"
      className={`relative block h-3.5 w-7 shrink-0 rounded-full border transition-colors ${
        on ? "border-primary/60 bg-primary/15" : "border-border"
      }`}
    >
      <span
        className={`absolute top-[1.5px] size-2.5 rounded-full transition-all duration-150 ${
          on ? "left-[14px] bg-primary" : "left-[2px] bg-muted-foreground/40"
        }`}
      />
    </span>
  );
}

function Legend({ items }: { items: { color: string; label: string; value?: string }[] }) {
  return (
    <ul className="mt-0.5 mb-1.5 ml-9 flex flex-col gap-0.5">
      {items.map((it) => (
        <li key={it.label} className="flex items-center gap-2 text-[0.66rem] text-muted-foreground">
          <span className="size-2 shrink-0 rounded-[2px]" style={{ background: it.color }} />
          <span className="truncate text-foreground/80">{it.label}</span>
          {it.value && <span className="ml-auto font-mono tabular-nums">{it.value}</span>}
        </li>
      ))}
    </ul>
  );
}

export interface LayerPanelProps {
  layers: Layers;
  onToggle: (key: LayerKey) => void;
  /** Undefined while a feed is still loading its first response. */
  counts: Partial<Record<LayerKey, number | undefined>>;
  feeds: Partial<Record<LayerKey, FeedState>>;
  sats: FireSat[];
  /** Detections in the loaded dataset per FIRMS platform label. */
  satDetections: Record<string, number>;
  /** EONET category counts, so the legend names only what is actually open. */
  eonetCategories: { id: string; label: string; count: number }[];
  onShowHelp: () => void;
}

export function LayerPanel({
  layers,
  onToggle,
  counts,
  feeds,
  sats,
  satDetections,
  eonetCategories,
  onShowHelp,
}: LayerPanelProps) {
  const total = LAYER_GROUPS.reduce((n, g) => n + g.layers.length, 0);
  const on = LAYER_GROUPS.reduce((n, g) => n + g.layers.filter((l) => layers[l.key]).length, 0);

  const legends: Partial<Record<LayerKey, ReactNode>> = {
    facilities: (
      <Legend
        items={FACILITY_LEGEND.map((k) => ({ color: FACILITY_COLORS[k] ?? "#71808f", label: k }))}
      />
    ),
    quakes: (
      <Legend
        items={[
          { color: QUAKE_COLOR.recent, label: "Past 24 hours" },
          { color: QUAKE_COLOR.day3, label: "Past 3 days" },
          { color: QUAKE_COLOR.older, label: "Past week" },
        ]}
      />
    ),
    eonet: (
      <Legend
        items={eonetCategories.slice(0, 8).map((c) => ({
          color: EONET_COLORS[c.id] ?? "#a1adba",
          label: c.label,
          value: c.count.toLocaleString(),
        }))}
      />
    ),
    sats: (
      <Legend
        items={sats.map((s) => ({
          color: s.color,
          label: `${s.name} ${s.instrument}`,
          value: satDetections[s.firmsLabel]
            ? `${satDetections[s.firmsLabel]!.toLocaleString()} det`
            : "none",
        }))}
      />
    ),
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <p className="text-sm font-semibold">Layers</p>
        <div className="flex items-center gap-2">
          <span className="font-mono text-[0.66rem] text-muted-foreground tabular-nums">
            {on} of {total} on
          </span>
          <button
            onClick={onShowHelp}
            title="Keyboard shortcuts"
            className="kbd hover:text-foreground"
          >
            ?
          </button>
        </div>
      </div>

      {LAYER_GROUPS.map((group) => {
        const active = group.layers.filter((l) => layers[l.key]).length;
        return (
          <div key={group.label}>
            <div className="mb-1 flex items-center gap-1.5 border-b border-border pb-1">
              <span className="field-label">{group.label}</span>
              <span className="ml-auto font-mono text-[0.62rem] text-muted-foreground tabular-nums">
                {active} of {group.layers.length}
              </span>
            </div>
            <div className="flex flex-col">
              {group.layers.map((l) => {
                const isOn = layers[l.key];
                const dormant = !!l.parent && !layers[l.parent];
                const count = counts[l.key];
                const feed = feeds[l.key];
                return (
                  <div key={l.key}>
                    <button
                      onClick={() => onToggle(l.key)}
                      aria-pressed={isOn}
                      className={`relative flex w-full items-center gap-2.5 rounded-sm py-1.5 pr-1 text-left hover:bg-muted ${
                        l.parent ? "pl-6" : "pl-1"
                      } ${dormant ? "opacity-40" : ""}`}
                    >
                      {l.parent && (
                        <span
                          aria-hidden
                          className="pointer-events-none absolute top-0 left-[10px] h-1/2 w-2 rounded-bl-[3px] border-b border-l border-border"
                        />
                      )}
                      <Switch on={isOn} />
                      <span className="min-w-0 flex-1">
                        <span
                          className={`block truncate text-[0.76rem] ${isOn ? "text-foreground" : "text-muted-foreground"}`}
                        >
                          {l.label}
                        </span>
                        {l.description && (
                          <span className="block truncate text-[0.66rem] text-muted-foreground/80">
                            {l.description}
                          </span>
                        )}
                      </span>
                      {count != null && (
                        <span className="font-mono text-[0.66rem] text-muted-foreground tabular-nums">
                          {count.toLocaleString()}
                        </span>
                      )}
                      {feed && (
                        <span
                          title={feedTitle(feed)}
                          className={`size-2 shrink-0 rounded-[2px] ${STATUS_DOT[feed.status]}`}
                        />
                      )}
                      <kbd className="kbd">{l.shortcut}</kbd>
                    </button>
                    {isOn && legends[l.key]}
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
