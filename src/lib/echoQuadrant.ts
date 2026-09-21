/**
 * Echo 384 source-plate column-parity geometry, mirrored from
 * kuma_core/kuro/plate_quadrant.py (read-only reference, not edited here).
 *
 * A 96-head Zephyr sits on a 9 mm pitch and a 384-well plate on 4.5 mm, so one
 * stamp reaches every other column. Rows are doubled as they always were:
 * 96-well `<row><col>` maps to 384 row `2r` for the forward primer and `2r + 1`
 * for the reverse, so forward primers sit on rows A C E G I K M O and reverse
 * primers on B D F H J L N P, always. Columns follow
 * `col_384 = (col - 1) * 2 + 1 + colOffset`, and the offset is the whole
 * choice: `A1` is the odd columns 1, 3 ... 23 and `A2` the even columns
 * 2, 4 ... 24.
 *
 * Two options and not four: the v0.14.0 picker also offered B1 and B2 and sent
 * reverse primers to a paired quadrant, which made the row axis a duplicate of
 * the column one. The python docstring carries that history, the three
 * vocabularies these names have had, the real Echo worklist that reads as
 * contiguous columns instead, and the operator statement of 2026-09-20 that
 * overrides it. Why that workbook looks the way it does is (미확인). Do not
 * flip this geometry a third time on a reading of that workbook alone.
 *
 * Why this module and not a table inside the picker: EchoPlateView needs the
 * same column rule to shade the wells this run does not touch, and two copies
 * of a geometry that mirrors a Python file would be two places to drift from
 * it.
 */
import { compareVersionParts, parseVersionParts } from "@/lib/mame/resultContract";
import type { EchoQuadrant } from "@/types/models";

/** The two column parities a round can take, in the order the UI offers them. */
export const ECHO_QUADRANTS: readonly EchoQuadrant[] = ["A1", "A2"] as const;

/** round -> 384 column offset (`_COL_OFFSETS` in python). */
const COLUMN_OFFSETS: Record<EchoQuadrant, 0 | 1> = {
  A1: 0,
  A2: 1,
};

/**
 * Interleaved-era names for the rounds this module already has
 * (`FOLDED_QUADRANTS` in python). `B1` was the odd columns seen from their
 * reverse rows and `B2` the even ones, so each folds onto its partner and not
 * one source well moves.
 */
const FOLDED_QUADRANTS: Record<string, EchoQuadrant> = { B1: "A1", B2: "A2" };

/**
 * Values only a project saved under the half layout can carry
 * (`LEGACY_QUADRANTS` in python). "A1" and "A2" are not among them: both are
 * current names too, so they are dated by the saved app version instead.
 */
const LEGACY_QUADRANTS: ReadonlySet<string> = new Set(["A13"]);

/** First release that wrote contiguous-half names. */
export const HALF_LAYOUT_VERSION = "0.16.61";

/**
 * First release that writes column-parity names again. A project saved at or
 * after it means parities, whatever the half era spelled the same way.
 */
export const QUADRANT_RESTORE_VERSION = "0.16.68";

const HALF_LAYOUT_PARTS: number[] = parseVersionParts(HALF_LAYOUT_VERSION) ?? [];
const QUADRANT_RESTORE_PARTS: number[] = parseVersionParts(QUADRANT_RESTORE_VERSION) ?? [];

/**
 * Was `version` written while a round was a contiguous half, i.e. in
 * [HALF_LAYOUT_VERSION, QUADRANT_RESTORE_VERSION)?
 *
 * The values no stored name can date are a lone "A1" and a lone "A2": the half
 * layout and this one spell them the same, and the half one meant columns 1-12
 * of every row rather than the odd columns. The saved app version is the only
 * signal that separates them.
 *
 * A version this cannot parse, including a file with no version at all, is
 * read as *not* half era. Every release that wrote half names also wrote this
 * stamp (kuroSnapshot.ts has carried it since v0.1.5.01, and the workspace
 * save gained it in 0.16.61 itself), so an absent stamp places the file before
 * 0.16.61, in the interleaved era whose names already mean what they say.
 * Reading absence as half era instead would drop the selection of every
 * project saved before 0.16.61 for no reason.
 *
 * Dotted segments are compared as numbers, never as strings, so "0.16.9" is
 * older than "0.16.61".
 */
export function savedUnderHalfLayout(version: unknown): boolean {
  if (typeof version !== "string") return false;
  const parts = parseVersionParts(version);
  if (parts === null) return false;
  return (
    compareVersionParts(parts, HALF_LAYOUT_PARTS) >= 0 &&
    compareVersionParts(parts, QUADRANT_RESTORE_PARTS) < 0
  );
}

/** What a stored Echo placement means under the column-parity layout. */
export interface PersistedEchoPlacement {
  /** Round this placement takes, or null when the operator has to pick again. */
  quadrant: EchoQuadrant | null;
  /** Rounds that are spent, in {@link ECHO_QUADRANTS} order. */
  usedQuadrants: EchoQuadrant[];
  /**
   * Every stored name of a placement written under the half layout, in the
   * order it was read and with the `quadrant` first. Empty for anything that
   * can be read without refusing, which includes a folded "B1". Callers report
   * it rather than re-deriving the rule.
   */
  legacySeen: string[];
}

/**
 * Read a stored Echo placement. This function is the rule, mirroring
 * `fold_persisted_placement` in kuma_core/kuro/plate_quadrant.py and adding
 * the version test that file cannot make (it is handed values, not files).
 *
 * Both fields are read together, because one half name dates the whole
 * placement: `quadrant="A13"` with `used=["A1"]` is a half-era project, and
 * that "A1" is columns 1-12 rather than the odd columns.
 *
 * A half-era placement yields `(null, ["A1", "A2"], <names>)`. A block of
 * twelve consecutive columns holds six odd columns and six even ones, so it
 * matches no parity and sits on 48 of the 192 wells of each round: neither is
 * clean, and folding it onto one would move every source well silently.
 *
 * An interleaved-era "B1" or "B2" folds onto "A1" or "A2" instead of being
 * refused. Those names denoted the very rounds this module has, seen from
 * their reverse rows, so the fold moves no coordinate and needs nothing from
 * the operator. It is therefore not reported in `legacySeen`.
 *
 * An empty placement stays empty whatever the version says. A project that
 * never chose a round has nothing to date, and reporting both rounds spent for
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
      names.some((name) => LEGACY_QUADRANTS.has(name)) || savedUnderHalfLayout(savedVersion);
    if (legacy) {
      return { quadrant: null, usedQuadrants: [...ECHO_QUADRANTS], legacySeen: names };
    }
  }

  const isRound = (name: string | null): name is EchoQuadrant =>
    name !== null && (ECHO_QUADRANTS as readonly string[]).includes(name);
  const fold = (name: string): string => FOLDED_QUADRANTS[name] ?? name;
  const folded = target === null ? null : fold(target);
  const spent = new Set(spentRaw.map(fold));
  return {
    quadrant: isRound(folded) ? folded : null,
    usedQuadrants: ECHO_QUADRANTS.filter((q) => spent.has(q)),
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
export type EchoPlacementIssue = "noQuadrantSelected" | "quadrantAlreadyUsed" | null;

export function echoPlacementIssue(
  quadrant: EchoQuadrant | null,
  usedQuadrants: readonly EchoQuadrant[],
): EchoPlacementIssue {
  if (quadrant === null) return usedQuadrants.length > 0 ? "noQuadrantSelected" : null;
  return usedQuadrants.includes(quadrant) ? "quadrantAlreadyUsed" : null;
}

/** 384 column offset (0 or 1) of `q`: 0 for A1, 1 for A2. */
export function quadrantColumnOffset(q: EchoQuadrant): 0 | 1 {
  return COLUMN_OFFSETS[q];
}

/** First 384 column (1-based) of `q`: 1 for A1, 2 for A2. */
export function quadrantFirstColumn(q: EchoQuadrant): number {
  return COLUMN_OFFSETS[q] + 1;
}

/** Last 384 column (1-based) of `q`: 23 for A1, 24 for A2. */
export function quadrantLastColumn(q: EchoQuadrant): number {
  return COLUMN_OFFSETS[q] + 23;
}

/**
 * Does the 384 well at `colNumber` (1-based) belong to the round `q`?
 *
 * Column parity is the whole answer, because the stamp skips every other
 * column. The row is not consulted: both row parities of these columns belong
 * to the round, the even ones carrying forward primers and the odd ones their
 * reverses. A contiguous range test here would mark the wells of the other
 * round as this one's over half the plate.
 */
export function isColumnInQuadrant(colNumber: number, q: EchoQuadrant): boolean {
  return (colNumber - 1) % 2 === COLUMN_OFFSETS[q];
}

/** The other round, i.e. the columns a run on `q` leaves untouched. */
export function otherQuadrants(q: EchoQuadrant): EchoQuadrant[] {
  return ECHO_QUADRANTS.filter((c) => c !== q);
}

/**
 * How many of the two rounds are spent once this run lands: the operator's
 * `usedQuadrants` plus the round this run takes, de-duplicated.
 */
export function quadrantsFilledAfterRun(q: EchoQuadrant, used: readonly EchoQuadrant[]): number {
  return new Set<EchoQuadrant>([...used, q]).size;
}

/**
 * Is the 384 row at `rowIdx` (0 = A) a forward-primer row?
 *
 * Row parity is the whole answer: a forward primer sits at `2r` and its
 * reverse at `2r + 1` in either round, and the no-quadrant fallback the mapper
 * uses when nothing is selected (`plate_mapper.py`) is row-doubled in the same
 * way. A round shifts columns only, so it is not an argument here. The v0.14.0
 * picker did make direction depend on the selection, by offering a row axis
 * that duplicated the column one; the python docstring says why that axis is
 * gone.
 */
export function isForwardRow(rowIdx: number): boolean {
  return rowIdx % 2 === 0;
}
