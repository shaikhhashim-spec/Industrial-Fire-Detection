import { investigationPriority } from "../../../site/investigations-data.mjs";
import type { ThermalEvent } from "@/lib/thermal";

const number = (value: unknown, unit = "") =>
  typeof value === "number" && Number.isFinite(value) && value >= 0
    ? `${Number(value.toFixed(1))}${unit}`
    : "Unavailable";

export function ThermalChange({ event }: { event: ThermalEvent }) {
  const priority = investigationPriority(event);
  const t = priority.thermal;
  const percent =
    typeof t.changePercent === "number" && Number.isFinite(t.changePercent)
      ? `${t.changePercent > 0 ? "+" : ""}${t.changePercent.toFixed(1)}%`
      : "Unavailable";
  const facts = [
    ["Baseline FRP", number(t.baselineFrp, " MW")],
    ["Current-day peak FRP", number(t.currentFrp, " MW")],
    ["Change", percent],
    ["Prior comparable days", number(t.observationDays)],
    ["Days without comparable observations", number(t.gaps)],
    ["Review priority", `${priority.points} pts`],
  ];
  return (
    <section
      aria-label="Thermal Change"
      className="min-w-0 border-y border-border py-3 text-[0.72rem] [overflow-wrap:anywhere]"
    >
      <h3 className="text-sm font-semibold">Thermal Change</h3>
      <p className="mt-1">{t.label}</p>
      <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-2">
        {facts.map(([label, value]) => (
          <div key={label} className="min-w-0">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="font-mono tabular-nums">{value}</dd>
          </div>
        ))}
      </dl>
      <ul className="mt-2 list-disc space-y-1 pl-4 text-muted-foreground">
        {t.reasons.map((reason: string, i: number) => (
          <li key={i}>{reason}</li>
        ))}
      </ul>
      <details className="mt-2 text-muted-foreground">
        <summary className="cursor-pointer">Priority reasons and limitations</summary>
        <ul className="mt-2 list-disc space-y-1 pl-4">
          {priority.contributions.map((c: { points: number; reason: string }, i: number) => (
            <li key={`priority-${i}`}>
              +{c.points} pts: {c.reason}
            </li>
          ))}
          {t.limitations.map((reason: string, i: number) => (
            <li key={`limit-${i}`}>{reason}</li>
          ))}
        </ul>
        <p className="mt-2">{priority.caveat}</p>
      </details>
    </section>
  );
}
