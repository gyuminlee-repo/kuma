/**
 * Pure helpers for the Current-Selection 3D Analysis panel.
 * No side effects, no store imports.
 */

import type { RankedCandidateItem } from "../types/models.generated";

const POS_RE = /[A-Z](\d+)[A-Z]/;

/**
 * Extract the 1-based reference position from a variant string.
 * Uses the same first-match semantics as kuma_core._POS_RE.
 * Returns undefined when no match is found.
 */
function extractRefPosition(variant: string): number | undefined {
  const m = POS_RE.exec(variant);
  return m !== undefined && m !== null ? parseInt(m[1], 10) : undefined;
}

export interface SelectedPositionRow {
  variant: string;
  refPosition: number;
  yPred: number;
}

/**
 * Derive per-variant rows from the current selection.
 *
 * For each variant in `selectedVariants`:
 *  - Look up its RankedCandidateItem for `aa_position` and `y_pred`.
 *  - If `aa_position` is null/undefined, fall back to regex extraction.
 *  - `y_pred` comes from the candidate item; if the item is missing, fall
 *    back to `yPredMap`; if neither exists, skip the variant.
 *  - Skip variants with no parseable position.
 *
 * No deduplication is performed here (return one row per selected variant).
 */
export function deriveSelectedPositions(
  selectedVariants: string[],
  ranked: RankedCandidateItem[],
  yPredMap: Record<string, number>,
): SelectedPositionRow[] {
  const candidateByVariant = new Map<string, RankedCandidateItem>();
  for (const item of ranked) {
    candidateByVariant.set(item.variant, item);
  }

  const rows: SelectedPositionRow[] = [];

  for (const variant of selectedVariants) {
    const candidate = candidateByVariant.get(variant);

    // Resolve y_pred: candidate > yPredMap > skip
    let yPred: number | undefined;
    if (candidate !== undefined) {
      yPred = candidate.y_pred;
    } else if (Object.prototype.hasOwnProperty.call(yPredMap, variant)) {
      yPred = yPredMap[variant];
    }
    if (yPred === undefined) continue;

    // Resolve refPosition: aa_position > regex > skip
    let refPosition: number | undefined;
    if (candidate !== undefined && candidate.aa_position != null) {
      refPosition = candidate.aa_position;
    } else {
      refPosition = extractRefPosition(variant);
    }
    if (refPosition === undefined) continue;

    rows.push({ variant, refPosition, yPred });
  }

  return rows;
}

/**
 * Return sorted unique refPositions from a set of selected-position rows.
 */
export function selectedRefPositions(rows: SelectedPositionRow[]): number[] {
  const seen = new Set<number>();
  for (const row of rows) seen.add(row.refPosition);
  return Array.from(seen).sort((a, b) => a - b);
}

export interface MappedYpredRow {
  accPosition: number;
  refPosition: number;
  yPred: number;
  variant: string;
}

export interface JoinResult {
  rows: MappedYpredRow[];
  /** True when remaining.length !== mapped.length (truncated to min). */
  lengthMismatch: boolean;
}

/**
 * Order-preserving join of selected rows with the dispersion result arrays.
 *
 * 1. Remove rows whose refPosition is in `dropped` (positions the backend
 *    could not map to the accession frame).
 * 2. Sort the remaining rows by refPosition ascending.
 * 3. Pair remaining[i].refPosition with mapped[i] (sorted ascending) to
 *    produce accPosition values.
 *
 * The monotonic sort guarantee means sorted-ref <-> sorted-accession is the
 * correct alignment (PDB residue numbering is monotonically related to
 * sequence position within a chain).
 *
 * Guards a length mismatch by truncating to min(remaining, mapped).
 */
export function joinMappedYpred(
  rows: SelectedPositionRow[],
  dropped: number[],
  mapped: number[],
): JoinResult {
  const droppedSet = new Set(dropped);

  const remaining = rows
    .filter((r) => !droppedSet.has(r.refPosition))
    .sort((a, b) => a.refPosition - b.refPosition);

  const sortedMapped = [...mapped].sort((a, b) => a - b);

  const len = Math.min(remaining.length, sortedMapped.length);
  const lengthMismatch = remaining.length !== sortedMapped.length;

  const out: MappedYpredRow[] = [];
  for (let i = 0; i < len; i++) {
    const r = remaining[i];
    out.push({
      accPosition: sortedMapped[i],
      refPosition: r.refPosition,
      yPred: r.yPred,
      variant: r.variant,
    });
  }

  return { rows: out, lengthMismatch };
}
