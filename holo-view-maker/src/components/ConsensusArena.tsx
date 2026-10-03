import { Scale, ScanEye, ShieldAlert } from "lucide-react";
import { evaluateConsensus } from "../../../site/consensus.mjs";
import type { ThermalEvent } from "@/lib/thermal";

export function ConsensusArena({ event }: { event: ThermalEvent }) {
  const result = evaluateConsensus(event);
  const roles = [
    { name: "Sentinel", icon: ShieldAlert, evidence: result.sentinel, color: "var(--critical)" },
    { name: "Skeptic", icon: ScanEye, evidence: result.skeptic, color: "var(--warn)" },
    { name: "Arbiter", icon: Scale, evidence: result.arbiter, color: "var(--primary)" },
  ];
  return (
    <section className="arena-section border-y border-border py-3" aria-label="Multi-Agent Arena">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-semibold">Multi-Agent Arena</h3>
        <span className="font-mono text-sm tabular-nums">{result.index}/100</span>
      </div>
      <p className="mt-1 text-[0.66rem] text-muted-foreground">
        Rule-based evidence screening / Evidence index
      </p>
      <div
        role="meter"
        aria-label="Evidence index, not a probability"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={result.index}
        className="mt-2 h-1.5 overflow-hidden rounded-sm bg-muted"
      >
        <div className="arena-meter h-full bg-primary" style={{ width: `${result.index}%` }} />
      </div>
      <p className="mt-2 text-[0.72rem] font-medium">{result.verdict}</p>
      <details className="mt-2">
        <summary className="cursor-pointer text-[0.7rem] text-primary">Evidence debate</summary>
        <div className="mt-2 flex flex-col gap-3">
          {roles.map(({ name, icon: Icon, evidence, color }) => (
            <div key={name} className="min-w-0">
              <div className="flex items-center gap-2 text-[0.72rem]">
                <Icon aria-hidden className="size-3.5 shrink-0" style={{ color }} />
                <h4 className="font-semibold">{name}</h4>
                <span className="ml-auto shrink-0 font-mono tabular-nums">
                  {evidence.points > 0 ? "+" : ""}
                  {evidence.points} pts
                </span>
              </div>
              <p className="mt-1 text-[0.7rem] leading-relaxed">{evidence.summary}</p>
              <ul className="mt-1 list-inside list-disc text-[0.66rem] leading-relaxed text-muted-foreground">
                {evidence.evidence.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          ))}
          <ul className="border-t border-border pt-2 text-[0.66rem] leading-relaxed text-muted-foreground">
            {result.limitations.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </details>
    </section>
  );
}
