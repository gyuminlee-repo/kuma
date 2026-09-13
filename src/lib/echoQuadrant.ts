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
import { compareVersionParts, parseVersionParts } from "@/lib/mame/resultContract";
import type { EchoQuadrant } from "@/types/models";

/** The two wells a round can start from, in the order the UI offers them. */
export const ECHO_QUADRANTS: readonly EchoQuadrant[] = ["A1", "A13"] as const;

/** half -> 384 column offset (`_COL_OFFSETS` in python). */
const COLUMN_OFFSETS: Record<EchoQuadrant, 0 | 12> = {
  A1: 0,
  A13: 12,
};

/**
 * Values only a project saved before the half layout can carry
 * (`LEGACY_QUADRANTS` in python). "A1" is not one of them: it is a current
 * half name too, so it is dated by the saved app version instead.
 */
const LEGACY_QUADRANTS: ReadonlySet<string> = new Set(["A2", "B1", "B2"]);

/**
 * First release that wrote half names. A project saved before it means the
 * old geometry even when every stored name is still spelled the same way.
 */
export const HALF_LAYOUT_VERSION = "0.16.59";

const HALF_LAYOUT_PARTS: number[] = parseVersionParts(HALF_LAYOUT_VERSION) ?? [];

/**
 * Was `version` written before the source plate became two halves?
 *
 * The one value the stored names cannot date is a lone "A1": the old layout
 * and this one spell it the same, and the old one meant the odd columns of
 * the whole plate rather than the left half. The saved app version is the
 * only signal that separates them, so anything this cannot parse, including
 * a file with no version at all, is read as old. Dotted segments are compared
 * as numbers, never as strings, so "0.16.9" is older than "0.16.59".
 */
export function predatesHalfLayout(version: unknown): boolean {
  if (typeof version !== "string") return true;
  const parts = parseVersionParts(version);
  if (parts === null) return true;
  return compareVersionParts(parts, HALF_LAYOUT_PARTS) < 0;
}

/** What a stored Echo placement means under the half layout. */
export interface PersistedEchoPlacement {
  /** Half this round takes, or null when the operator has to pick again. */
  quadrant: EchoQuadrant | null;
  /** Halves that are spent, in {@link ECHO_QUADRANTS} order. */
  usedQuadrants: EchoQuadrant[];
  /**
   * Every stored name of a placement that predates the half layout, in the
   * order it was read and with the `quadrant` first. Empty for a placement
   * this version wrote. Callers report it rather than re-deriving the rule.
   */
  legacySeen: string[];
}

/**
 * Read a stored Echo placement. This function is the rule, mirroring
 * `fold_persisted_placement` in kuma_core/kuro/plate_quadrant.py and adding
 * the version test that file cannot make (it is handed values, not files).
 *
 * Both fields are read together, because one old value dates the whole
 * placement: `quadrant="B2"` with `used=["A1"]` is an old project, and that
 * "A1" is an odd-column interleaved set rather than the left half.
 *
 * An old placement yields `(null, ["A1", "A13"], <old values>)`: every old
 * value spanned the full plate width, so both halves hold primers and no half
 * is a legitimate selection. A current placement passes through unchanged,
 * with unknown entries dropped and halves de-duplicated.
 *
 * An empty placement stays empty whatever the version says. A project that
 * never chose a half has nothing to date, and reporting both halves spent for
 * it would invent a plate state the operator never stated.
 *
 * Unlike the python side, non-string entries are dropped rather than raising:
 * this reads a JSON file straight off disk, where the core reads values
 * Pydantic has already typed.
 */
export function foldPersistedPlacement(
  quadrant: unknown,
  usedQuadrants: readonly unknown[],
  savedVersion: unknown,
): PersistedEchoPlacement {
  const normalize = (value: unknown): string | null => {
    if (typeof value !== "string") return null;
    const name = value.trim().toUpperCase();
    return name.length > 0 ? name : null;
  };
  const target = normalize(quadrant);
  const spentRaw = usedQuadrants.map(normalize).filter((n): n is string => n !== null);
  const names = (target === null ? [] : [target]).concat(spentRaw);

  if (names.length > 0) {
    const legacy =
      names.some((name) => LEGACY_QUADRANTS.has(name)) || predatesHalfLayout(savedVersion);
    if (legacy) {
      return { quadrant: null, usedQuadrants: [...ECHO_QUADRANTS], legacySeen: names };
    }
  }

  const spent = new Set(spentRaw);
  const isHalf = (name: string | null): name is EchoQuadrant =>
    name !== null && (ECHO_QUADRANTS as readonly string[]).includes(name);
  return {
    quadrant: isHalf(target) ? target : null,
    usedQuadrants: ECHO_QUADRANTS.filter((half) => spent.has(half)),
    legacySeen: [],
  };
}

/**
 * Why a placement cannot be sent to the sidecar, or null when it can.
 *
 * The sidecar refuses both of these (`plate_mapper.py`,
 * `check_quadrants_available`), and its message is an English sentence aimed
 * at a developer. Testing the same two conditions here keeps that string off
 * the screen and lets the UI say what to do instead.
 */
export type EchoPlacementIssue = "noHalfSelected" | "halfAlreadyUsed" | null;

export function echoPlacementIssue(
  quadrant: EchoQuadrant | null,
  usedQuadrants: readonly EchoQuadrant[],
): EchoPlacementIssue {
  if (quadrant === null) return usedQuadrants.length > 0 ? "noHalfSelected" : null;
  return usedQuadrants.includes(quadrant) ? "halfAlreadyUsed" : null;
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
