/**
 * Echo 384 source-plate quadrant geometry, mirrored from
 * kuma_core/kuro/plate_quadrant.py (read-only reference, not edited here).
 *
 * A 96-head Zephyr sits on a 9 mm pitch and a 384-well plate on 4.5 mm, so one
 * stamp reaches every other row *and* every other column: 8 x 12 = 96 wells.
 * The four starting wells (A1/A2/B1/B2) name the four interleaved sets, and
 * those four sets tile the plate. Four contiguous blocks are not one of them;
 * that layout is unreachable with this head.
 *
 * Why this module and not a table inside the picker: PlateQuadrantPicker held
 * a private `pairedQuadrant`, and EchoPlateView now needs the same offsets to
 * shade the wells this run does not touch. Two copies of a geometry that
 * mirrors a Python file would be two places to drift from it.
 */
import type { EchoQuadrant } from "@/types/models";

/** The four wells a 96-head can start from, in the order the UI offers them. */
export const ECHO_QUADRANTS: readonly EchoQuadrant[] = ["A1", "A2", "B1", "B2"] as const;

/** quadrant -> [row offset, column offset], both 0 or 1 (`_OFFSETS` in python). */
const OFFSETS: Record<EchoQuadrant, readonly [0 | 1, 0 | 1]> = {
  A1: [0, 0],
  A2: [0, 1],
  B1: [1, 0],
  B2: [1, 1],
};

/**
 * Reverse-primer quadrant that goes with `q`: A1<->B1, A2<->B2.
 *
 * Forward and reverse stay on adjacent rows of the same columns, so a run
 * spends a *pair* of quadrants and one plate holds two rounds.
 */
export function pairedQuadrant(q: EchoQuadrant): EchoQuadrant {
  const [row, col] = OFFSETS[q];
  const partner = ECHO_QUADRANTS.find((c) => OFFSETS[c][1] === col && OFFSETS[c][0] !== row);
  // Every offset pair has a partner by construction; the guard keeps the
  // return type free of `undefined` without a cast.
  if (!partner) throw new Error(`no partner for quadrant ${q}`);
  return partner;
}

/** Column offset (0 or 1) of `q`. Its pair shares it. */
export function quadrantColumnOffset(q: EchoQuadrant): 0 | 1 {
  return OFFSETS[q][1];
}

/**
 * Does the 384 well at `colNumber` (1-based) belong to the pair `q` spends?
 *
 * Column parity alone decides it: `q` and `pairedQuadrant(q)` share a column
 * offset and differ only in row offset, so the run covers both row parities of
 * those columns. Testing the row as well would mark every reverse-primer well
 * as belonging to another run.
 */
export function isColumnInQuadrantPair(colNumber: number, q: EchoQuadrant): boolean {
  return (colNumber - 1) % 2 === quadrantColumnOffset(q);
}

/** The other pair, i.e. the two quadrants a run on `q` leaves untouched. */
export function otherQuadrantPair(q: EchoQuadrant): EchoQuadrant[] {
  const mine = new Set<EchoQuadrant>([q, pairedQuadrant(q)]);
  return ECHO_QUADRANTS.filter((c) => !mine.has(c));
}

/**
 * How many of the four quadrants are spent once this run lands: the operator's
 * `usedQuadrants` plus the pair this run takes, de-duplicated.
 */
export function quadrantsFilledAfterRun(q: EchoQuadrant, used: readonly EchoQuadrant[]): number {
  return new Set<EchoQuadrant>([...used, q, pairedQuadrant(q)]).size;
}

/**
 * Is the 384 row at `rowIdx` (0 = A) a forward-primer row for this run?
 *
 * Row parity alone is not the answer. The forward quadrant carries a row
 * offset (`OFFSETS[q][0]`), so a run on B1 or B2 puts its forward wells on
 * *odd* rows and its reverse wells on even ones, exactly inverting the old
 * `rowIdx % 2 === 0` rule.
 *
 * `q === null` is the legacy row-doubled layout the mapper falls back to when
 * no quadrant is selected (`plate_mapper.py:789-799`). There even rows really
 * are forward, and that fallback is the only case the bare parity rule was
 * ever right about.
 */
export function isForwardRow(rowIdx: number, q: EchoQuadrant | null): boolean {
  return rowIdx % 2 === (q === null ? 0 : OFFSETS[q][0]);
}
