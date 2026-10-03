import type { ConsensusEvent, ConsensusResult, PlumeInput } from "./consensus.mjs";
export interface LocationEvent extends ConsensusEvent {}
export function formatLocation(event: LocationEvent): string;
export const RISK_COLORS: Record<string, string>;
export const PERSISTENT_COLOR: string;
export const ACCENT: string;
export const MUTED: string;
export const SERIES: string;
export const CATEGORY_COLORS: Record<string, string>;
export interface Alert extends ConsensusEvent {
  id: string; title: string; severity: string; riskScore: number; priority: number | null;
  days: number; frp: number; classification: string; location: string;
  consensus: ConsensusResult; plume: PlumeInput | null;
  riskSummary: string | null; riskFactors: unknown[]; actions: unknown[]; reasons: string[];
}
export function alertsFrom(events?: (ConsensusEvent & {
  id?: string; riskLevel?: string; riskScore?: number; category?: string;
  priority?: number | null; riskSummary?: string | null; riskFactors?: unknown[];
  actions?: unknown[]; reasons?: string[];
})[] | null): Alert[];
export function matchAlerts(alerts: Alert[], query: string): Alert[];
export function summarize(data: { events?: (ConsensusEvent & { riskLevel?: string })[]; meta?: {
  observations?: number; persistentSources?: number; statesWithActivity?: number; satellites?: string[];
} }): { observations: number | null; events: number; persistent: number; atSites: number;
  critical: number; high: number; activePlumes: number; states: number; satellites: string[] };
export function satelliteLabel(name: string): string;
export function urgencyColor(urgency: string): string;
export function fmtUpdated(iso: string): string;
export function fmtAge(iso: string, now?: number): string;
