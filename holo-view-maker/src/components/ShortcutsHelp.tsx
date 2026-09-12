import { X } from "lucide-react";
import { LAYER_GROUPS } from "@/lib/layers";

const GENERAL = [
  { key: "R", desc: "Toggle auto-rotate" },
  { key: "?", desc: "Show / hide this help" },
  { key: "Esc", desc: "Close selection and popups" },
];

export function ShortcutsHelp({ onClose }: { onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-label="Keyboard shortcuts"
        className="panel w-[22rem] max-w-full p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <span className="text-sm font-semibold">Keyboard shortcuts</span>
          <button
            onClick={onClose}
            className="text-muted-foreground transition-colors duration-150 hover:text-foreground"
          >
            <X className="size-4" />
          </button>
        </div>
        {LAYER_GROUPS.map((g) => (
          <div key={g.label} className="mb-2">
            <p className="field-label mb-1">{g.label}</p>
            {g.layers.map((l) => (
              <div key={l.key} className="flex items-center justify-between py-0.5 text-[0.72rem]">
                <span className="text-muted-foreground">Toggle {l.label.toLowerCase()}</span>
                <kbd className="kbd">{l.shortcut}</kbd>
              </div>
            ))}
          </div>
        ))}
        <p className="field-label mb-1">General</p>
        {GENERAL.map((s) => (
          <div key={s.key} className="flex items-center justify-between py-0.5 text-[0.72rem]">
            <span className="text-muted-foreground">{s.desc}</span>
            <kbd className="kbd">{s.key}</kbd>
          </div>
        ))}
      </div>
    </div>
  );
}
