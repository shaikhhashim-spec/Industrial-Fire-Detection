export interface ThermalChange {
  status: "elevated" | "reduced" | "stable" | "insufficient_history";
  label: string;
  baselineFrp: number | null;
  currentFrp: number | null;
  changePercent: number | null;
  /** Prior comparable days, excluding the current acquisition day. */
  observationDays: number;
  /** Unmatched calendar days from first available prior observation to current. */
  gaps: number;
  limitations: string[];
  reasons: string[];
  priorityPoints: number;
}
export interface ThermalHistoryObservation {
  date?: string | null;
  frp?: number | null;
  frpObserved?: boolean | null;
  confidence?: number | null;
  satellite?: string | null;
  instrument?: string | null;
  daynight?: string | null;
  synthetic?: boolean;
}
export interface ThermalChangeEvent {
  acqDate?: string | null;
  history?: ThermalHistoryObservation[] | null;
  historyTruncated?: boolean;
}
export function analyzeThermalChange(event?: ThermalChangeEvent | null): ThermalChange;
