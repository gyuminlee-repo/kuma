import type { SdmPrimerResult } from "../types/models";

/**
 * Suggested retry parameters extracted from successful primers in the current
 * design run. Median values nudged slightly outward give a starting point that
 * already worked for similar mutations, instead of forcing the user to guess.
 */
export interface SuggestedRetryParams {
  tmFwd: number;
  tmRev: number;
  tmOverlap: number;
  gcMin: number;
  gcMax: number;
  fwdLenMin: number;
  fwdLenMax: number;
  revLenMin: number;
  revLenMax: number;
  tolMax: number;
  /** how many successful primers contributed to the suggestion. */
  sampleSize: number;
}

function median(values: number[]): number {
  if (values.length === 0) return NaN;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[mid - 1] + sorted[mid]) / 2
    : sorted[mid];
}

const FALLBACK = {
  tmFwd: 62,
  tmRev: 58,
  tmOverlap: 42,
  gcMin: 35,
  gcMax: 65,
  fwdLenMin: 22,
  fwdLenMax: 35,
  revLenMin: 18,
  revLenMax: 30,
  tolMax: 5,
};

/**
 * Build retry suggestion from successful primers.
 * Tm: median of observed Tm
 * GC: span of [min(observed) - 5, max(observed) + 5] clamped to [10, 90]
 * Length: span of [min(observed) - 2, max(observed) + 2] clamped to [15, 60]
 * tolMax: 6°C (one step above default 4°C)
 *
 * Falls back to user-provided defaults when sample size is zero.
 */
export function suggestRetryParams(
  results: SdmPrimerResult[],
  defaults: {
    tmFwd: number;
    tmRev: number;
    tmOverlap: number;
    gcMin: number;
    gcMax: number;
    fwdLenMin: number;
    fwdLenMax: number;
    revLenMin: number;
    revLenMax: number;
  } = FALLBACK,
): SuggestedRetryParams {
  if (results.length === 0) {
    return { ...defaults, tolMax: 6, sampleSize: 0 };
  }

  const tmFwds = results.map((r) => r.tm_no_fwd).filter((v) => Number.isFinite(v));
  const tmRevs = results.map((r) => r.tm_no_rev).filter((v) => Number.isFinite(v));
  const tmOvs = results
    .map((r) => (r as { tm_no_overlap?: number }).tm_no_overlap ?? defaults.tmOverlap)
    .filter((v) => Number.isFinite(v));
  const gcs = [
    ...results.map((r) => r.gc_fwd),
    ...results.map((r) => r.gc_rev),
  ].filter((v) => Number.isFinite(v));
  const fwdLens = results.map((r) => r.fwd_len).filter((v) => Number.isFinite(v));
  const revLens = results.map((r) => r.rev_len).filter((v) => Number.isFinite(v));

  const gcMinObs = gcs.length > 0 ? Math.min(...gcs) : defaults.gcMin;
  const gcMaxObs = gcs.length > 0 ? Math.max(...gcs) : defaults.gcMax;
  const fwdMinObs = fwdLens.length > 0 ? Math.min(...fwdLens) : defaults.fwdLenMin;
  const fwdMaxObs = fwdLens.length > 0 ? Math.max(...fwdLens) : defaults.fwdLenMax;
  const revMinObs = revLens.length > 0 ? Math.min(...revLens) : defaults.revLenMin;
  const revMaxObs = revLens.length > 0 ? Math.max(...revLens) : defaults.revLenMax;

  return {
    tmFwd: roundTo(median(tmFwds), 1),
    tmRev: roundTo(median(tmRevs), 1),
    tmOverlap: roundTo(median(tmOvs), 1),
    gcMin: clamp(Math.floor(gcMinObs - 5), 10, 90),
    gcMax: clamp(Math.ceil(gcMaxObs + 5), 10, 95),
    fwdLenMin: clamp(fwdMinObs - 2, 15, 60),
    fwdLenMax: clamp(fwdMaxObs + 2, 15, 60),
    revLenMin: clamp(revMinObs - 2, 15, 60),
    revLenMax: clamp(revMaxObs + 2, 15, 60),
    tolMax: 6,
    sampleSize: results.length,
  };
}

function roundTo(value: number, digits: number): number {
  if (!Number.isFinite(value)) return value;
  const k = 10 ** digits;
  return Math.round(value * k) / k;
}

function clamp(value: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, value));
}

export const STAGE_RELAXATION_TABLE = {
  1: { lengthDelta: 2, gcDelta: 0, tmTolDelta: 0 },
  2: { lengthDelta: 2, gcDelta: 3, tmTolDelta: 0 },
  3: { lengthDelta: 3, gcDelta: 5, tmTolDelta: 2 },
  4: { lengthDelta: 4, gcDelta: 8, tmTolDelta: 5 },
} as const;

export type CascadeStage = 1 | 2 | 3 | 4;

export function getStageRelaxation(stage: CascadeStage) {
  return STAGE_RELAXATION_TABLE[stage];
}

export interface StageParamsInput {
  tmFwd: number;
  tmRev: number;
  tmOverlap: number;
  gcMin: number;
  gcMax: number;
  fwdLenMin: number;
  fwdLenMax: number;
  revLenMin: number;
  revLenMax: number;
  baseTol: number;
}

export function getStageParams(base: StageParamsInput, stage: CascadeStage) {
  const r = STAGE_RELAXATION_TABLE[stage];
  return {
    tmFwd: base.tmFwd,
    tmRev: base.tmRev,
    tmOverlap: base.tmOverlap,
    gcMin: clamp(base.gcMin - r.gcDelta, 10, 90),
    gcMax: clamp(base.gcMax + r.gcDelta, 10, 95),
    fwdLenMin: base.fwdLenMin,
    fwdLenMax: clamp(base.fwdLenMax + r.lengthDelta, 15, 60),
    revLenMin: base.revLenMin,
    revLenMax: clamp(base.revLenMax + r.lengthDelta, 15, 60),
    tolMax: Math.min(10.0, base.baseTol + r.tmTolDelta),
  };
}
