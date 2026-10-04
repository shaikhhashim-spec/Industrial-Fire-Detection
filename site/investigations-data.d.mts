export interface ThermalChangeSummary {
  status: "insufficient_history" | "elevated" | "reduced" | "stable";
  label: string;
  baselineFrp: number | null;
  currentFrp: number | null;
  changePercent: number | null;
  observationDays: number;
  gaps: number;
  limitations: string[];
  reasons: string[];
  priorityPoints: number;
}

export interface InvestigationPriority {
  points: number;
  contributions: { label: string; points: number; reason: string }[];
  thermal: ThermalChangeSummary;
  caveat: string;
}

export function investigationPriority(event: object): InvestigationPriority;
