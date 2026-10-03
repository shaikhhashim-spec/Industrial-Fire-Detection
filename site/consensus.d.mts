export interface EvidenceContribution { key: string; points: number; reason: string }
export interface ConsensusRole { summary: string; points: number; evidence: string[] }
export interface ConsensusResult {
  mode: "rule-based";
  /** Heuristic evidence strength, not probability or confirmed fire. */
  index: number;
  verdict: "Verification required";
  limitations: string[];
  sentinel: ConsensusRole;
  skeptic: ConsensusRole;
  arbiter: ConsensusRole;
}
export interface PlumeInput {
  source?: string; estimated?: boolean; observedAt?: string | null;
  windSpeedKmh?: number | null; coneLengthKm?: number | null;
  downwindBearingDeg?: number | null;
}
export interface CompactPlume {
  windSpeedKmh: number; coneLengthKm: number; downwindBearingDeg: number;
  direction: string; label: string; estimated: true;
}
export interface ConsensusEvent {
  region?: string | null; district?: string | null; state?: string | null; country?: string | null;
  place?: { name?: string; country?: string | null; distanceKm?: number | null; direction?: string | null } | null;
  latitude?: number | null; longitude?: number | null;
  frp?: number | null; confidence?: number | null;
  persistenceDays?: number | null; detectionCount?: number | null;
  nightPasses?: number | null; lowConfidenceShare?: number | null;
  satellite?: string | null; satellites?: string[];
  corroborated?: boolean; facility?: { name?: string; distanceKm?: number | null } | null;
  model?: unknown; plume?: PlumeInput | null;
  evidence?: {
    maxFrp?: number | null; meanConfidence?: number | null;
    days?: number | null; detections?: number | null;
    nightPasses?: number | null; lowConfidenceShare?: number | null;
    satellites?: string[];
  } | null;
}
export function evaluateConsensus(event?: ConsensusEvent | null): ConsensusResult;
export function compactPlume(plume?: PlumeInput | null): CompactPlume | null;
export function compass16(bearing?: number | null): string | null;
export function validCoordinates(latitude: unknown, longitude: unknown): boolean;
