/**
 * Echo 384 source-plate half geometry, mirrored from
 * kuma_core/kuro/plate_quadrant.py (read-only reference, not edited here).
 *
 * A 384 source plate holds two rounds of a primer set. One round occupies the
 * left half (columns 1-12) and the next occupies the right half (columns
 * 13-24). Within a half the geometry is row-doubled: 96-well `<row><col>` maps
 * to 384 row `2r` for the forward primer and `2r + 1` for the reverse, with the
 * column carried over plus the half offset. Forward primers therefore sit on
 * rows A C E G I K M O and reverse primers on B D F H J L N P, always.
 *
 * The reference is the worklist the lab actually ran (`Project2-1. primer
 * dispensing (Echo525).xlsx`, 190 transfers, and `260417_echo_mapping.csv`,
 * 760 transfers). The interleaved four-quadrant layout this module used to
 * describe was read off a video in 2026-07-31 and does not exist on the bench;
 * the docstring in plate_quadrant.py carries the evidence.
 *
 * Why this module and not a table inside the picker: EchoPlateView needs the
 * same column offsets to shade the wells this run does not touch, and two
 * copies of a geometry that mirrors a Python file would be two places to drift
 * from it.
 */
import type { EchoQuadrant, PersistedEchoQuadrant } from "@/types/models";

/** The two wells a round can start from, in the order the UI offers them. */
export const ECHO_QUADRANTS: readonly EchoQuadrant[] = ["A1", "A13"] as const;

/** half -> 384 column offset (`_COL_OFFSETS` in python). */
const COLUMN_OFFSETS: Record<EchoQuadrant, 0 | 12> = {
  A1: 0,
  A13: 12,
};

/**
 * Values a project saved before the half layout can carry, and the half each
 * folds onto (`_LEGACY_FOLD` in python). The old A1/B1 pair was the left
 * columns and A2/B2 the right.
 */
const LEGACY_FOLD: Record<PersistedEchoQuadrant, EchoQuadrant> = {
  A1: "A1",
  B1: "A1",
  A2: "A13",
  B2: "A13",
  A13: "A13",
};

/**
 * Canonical half for a value read back from a saved project, or `null` for
 * anything this app never wrote.
 *
 * Load paths call this rather than testing membership themselves: a project
 * saved with `A13` must survive a reopen, and one saved under the old four-way
 * names must fold instead of being silently dropped. Folding is the
 * conservative direction, as a folded `used_quadrants` marks more of the plate
 * as spent than it may be and the core prefers a refusal over dispensing on
 * top of primers that are already there.
 */
export function foldLegacyQuadrant(value: unknown): EchoQuadrant | null {
  if (typeof value !== "string") return null;
  return LEGACY_FOLD[value as PersistedEchoQuadrant] ?? null;
}

/**
 * Fold a stored `used_quadrants` list, dropping unknown entries and
 * de-duplicating. `["A1", "B1"]` was one half stated twice under the old
 * names, so it folds to `["A1"]` rather than to a repeated entry.
 */
export function foldLegacyQuadrants(values: readonly unknown[]): EchoQuadrant[] {
  const folded: EchoQuadrant[] = [];
  for (const value of values) {
    const half = foldLegacyQuadrant(value);
    if (half !== null && !folded.includes(half)) folded.push(half);
  }
  return folded;
}

/** First 384 column (1-based) of `q`: 1 for A1, 13 for A13. */
export function quadrantFirstColumn(q: EchoQuadrant): number {
  return COLUMN_OFFSETS[q] + 1;
}

/** Last 384 column (1-based) of `q`: 12 for A1, 24 for A13. */
export function quadrantLastColumn(q: EchoQuadrant): number {
  return COLUMN_OFFSETS[q] + 12;
}

/**
 * Does the 384 well at `colNumber` (1-based) belong to the half `q`?
 *
 * Columns are contiguous, so this is a range test. The row is not consulted:
 * both row parities of these columns belong to the half, the even ones
 * carrying forward primers and the odd ones their reverses.
 */
export function isColumnInHalf(colNumber: number, q: EchoQuadrant): boolean {
  return colNumber >= quadrantFirstColumn(q) && colNumber <= quadrantLastColumn(q);
}

/** The other half, i.e. the columns a run on `q` leaves untouched. */
export function otherHalves(q: EchoQuadrant): EchoQuadrant[] {
  return ECHO_QUADRANTS.filter((c) => c !== q);
}

/**
 * How many of the two halves are spent once this run lands: the operator's
 * `usedQuadrants` plus the half this run takes, de-duplicated.
 */
export function quadrantsFilledAfterRun(q: EchoQuadrant, used: readonly EchoQuadrant[]): number {
  return new Set<EchoQuadrant>([...used, q]).size;
}

/**
 * Is the 384 row at `rowIdx` (0 = A) a forward-primer row?
 *
 * Row parity is the whole answer under the half layout: a forward primer sits
 * at `2r` and its reverse at `2r + 1` in either half, and the no-half fallback
 * the mapper uses when nothing is selected (`plate_mapper.py`) is row-doubled
 * in the same way. A half shifts columns only, so it is not an argument here.
 */
export function isForwardRow(rowIdx: number): boolean {
  return rowIdx % 2 === 0;
}
