/**
 * Split a design past one plate into export rounds of one plate each.
 *
 * The split happens here, at the boundary between the designed primers and
 * their plate mappings, so `export_all` and the plate mapper only ever
 * receive one plate.
 * Raising their cap instead would route the overflow through `_chunk_by_plate`
 * and its `P2-` labels, a plate nobody prepared (see `inputThresholds.ts`).
 *
 * There is no limit on the number of rounds. One Echo 384 source plate holds
 * two rounds, one per column parity, so a design past two rounds goes onto a
 * second source plate. Which plate and which parity (A1 or A2) a round takes
 * is not decided here. The operator picks both per round, because the source
 * plates are physical objects this program never sees
 * (`kuma_core/kuro/plate_quadrant.py`).
 */
import type { EchoQuadrant, PlateMapping } from "@/types/models";
import { ECHO_QUADRANTS } from "@/lib/echoQuadrant";
import { MAX_MUTATIONS_PER_RUN } from "@/lib/inputThresholds";
import { reorderMappings } from "@/lib/plate-utils";

/**
 * Folder suffix of a round: `R` and its 1-based number. Mirrors the
 * `round_label` pattern `^R[1-9][0-9]*$` in python.
 */
export type RoundLabel = `R${number}`;

export function roundLabel(index: number): RoundLabel {
  return `R${index + 1}`;
}

/** One round: its mappings on a single plate and the reverse dedup they use. */
export interface PlateRound {
  label: RoundLabel;
  /** 1-based position of the first and last forward primer in the full order. */
  from: number;
  to: number;
  mappings: PlateMapping[];
  dedupInfo: Record<string, string[]>;
}

/**
 * Echo source plate (1-based) and column parity picked for one round. Both
 * are null until the operator picks them; neither has a default.
 */
export interface RoundPick {
  plate: number | null;
  quadrant: EchoQuadrant | null;
}

/** One pick per round, index 0 for R1. A missing index is an unpicked round. */
export type RoundPicks = RoundPick[];

const UNPICKED: RoundPick = { plate: null, quadrant: null };

export function pickAt(picks: readonly RoundPick[], index: number): RoundPick {
  return picks[index] ?? UNPICKED;
}

/**
 * Source plate numbers the picker offers for `roundCount` rounds: one per
 * round, more than the ceil(rounds / 2) plates the design needs, so an
 * operator can put rounds on plates of their own choosing.
 */
export function plateOptionCount(roundCount: number): number {
  return Math.max(1, roundCount);
}

/**
 * The picks as they apply to a design of `roundCount` rounds: one per round,
 * and a round whose plate is past `plateOptionCount(roundCount)` unpicked.
 *
 * A saved pick can name a plate the picker no longer offers once the design
 * has fewer rounds. The select then shows nothing while the value would still
 * go out as `source_plate`, so the whole round is asked again instead. This is
 * the one place that rule lives; stored picks reach the export form and the
 * preview only through it. Returns `picks` itself when nothing changes, so a
 * caller can tell whether a write is needed.
 */
export function fitRoundPicks(picks: RoundPicks, roundCount: number): RoundPicks {
  const maxPlate = plateOptionCount(roundCount);
  const fitted = Array.from({ length: roundCount }, (_, k) => {
    const pick = pickAt(picks, k);
    return pick.plate !== null && pick.plate > maxPlate ? UNPICKED : pick;
  });
  const same = fitted.length === picks.length && fitted.every((p, k) => p === picks[k]);
  return same ? picks : fitted;
}

/** Does a selection of `count` forward primers need more than one round? */
export function needsRounds(count: number): boolean {
  return count > MAX_MUTATIONS_PER_RUN;
}

/**
 * Split `mappings` into rounds of at most `MAX_MUTATIONS_PER_RUN` forward
 * primers, in `sortedMutations` order (or the stored forward order when no
 * sort is active), numbered R1, R2 .. Rn.
 *
 * Each round's wells are re-indexed from A1, and its reverse primers are the
 * ones its own forward primers need, so a reverse shared across the boundary
 * is written in both rounds: each round is dispensed on its own. Returns an
 * empty list for no forward primers.
 */
export function splitIntoRounds(
  mappings: PlateMapping[],
  dedupInfo: Record<string, string[]>,
  sortedMutations: string[] | null,
): PlateRound[] {
  const fwdAll = mappings.filter((m) => m.primer_type === "forward");
  const revAll = mappings.filter((m) => m.primer_type !== "forward");

  const fwdMuts = fwdAll.map((m) => m.mutation);
  const fwdSet = new Set(fwdMuts);
  const order: string[] = [];
  const seen = new Set<string>();
  // Same order reorderMappings produces: the sort first, then any forward
  // primer the sort does not name (custom additions).
  for (const mut of [...(sortedMutations ?? []), ...fwdMuts]) {
    if (fwdSet.has(mut) && !seen.has(mut)) {
      seen.add(mut);
      order.push(mut);
    }
  }

  const roundCount = Math.ceil(order.length / MAX_MUTATIONS_PER_RUN);

  const rounds: PlateRound[] = [];
  for (let k = 0; k < roundCount; k++) {
    const muts = order.slice(k * MAX_MUTATIONS_PER_RUN, (k + 1) * MAX_MUTATIONS_PER_RUN);
    const mutSet = new Set(muts);
    const roundDedup: Record<string, string[]> = {};
    for (const [seq, group] of Object.entries(dedupInfo)) {
      const kept = group.filter((m) => mutSet.has(m));
      if (kept.length > 0) roundDedup[seq] = kept;
    }
    const roundFwd = fwdAll.filter((m) => mutSet.has(m.mutation));
    const roundMappings = reorderMappings([...roundFwd, ...revAll], roundDedup, muts);
    rounds.push({
      label: roundLabel(k),
      from: k * MAX_MUTATIONS_PER_RUN + 1,
      to: k * MAX_MUTATIONS_PER_RUN + muts.length,
      mappings: roundMappings,
      dedupInfo: roundDedup,
    });
  }
  return rounds;
}

/**
 * Parities already spent on round `index`'s source plate when it is
 * dispensed: the ones earlier rounds on the same plate picked, and on plate 1
 * the ones the operator marked as spent (`declaredUsed`). A plate past 1 is a
 * new plate, so nothing declared applies to it. This is the `used_quadrants`
 * the sidecar is sent. A round with no plate picked has nothing spent.
 */
export function usedBeforeRound(
  picks: readonly RoundPick[],
  index: number,
  declaredUsed: readonly EchoQuadrant[],
): EchoQuadrant[] {
  const plate = pickAt(picks, index).plate;
  if (plate === null) return [];
  const used = new Set<EchoQuadrant>(plate === 1 ? declaredUsed : []);
  for (const earlier of picks.slice(0, index)) {
    if (earlier.plate === plate && earlier.quadrant !== null) used.add(earlier.quadrant);
  }
  return ECHO_QUADRANTS.filter((q) => used.has(q));
}

export type RoundPickIssue =
  | "plateUnpicked"
  | "quadrantUnpicked"
  | "duplicate"
  | "quadrantAlreadyUsed";

/**
 * Why round `index` cannot be exported yet, or null when it can. Unlike
 * `usedBeforeRound` this looks at every other round, not only earlier ones:
 * a later round picked first must still stop an earlier one from taking the
 * same plate and parity.
 */
export function roundPickIssue(
  picks: readonly RoundPick[],
  index: number,
  declaredUsed: readonly EchoQuadrant[],
): RoundPickIssue | null {
  const { plate, quadrant } = pickAt(picks, index);
  if (plate === null) return "plateUnpicked";
  if (quadrant === null) return "quadrantUnpicked";
  const clash = picks.some(
    (other, j) => j !== index && other.plate === plate && other.quadrant === quadrant,
  );
  if (clash) return "duplicate";
  if (plate === 1 && declaredUsed.includes(quadrant)) return "quadrantAlreadyUsed";
  return null;
}

/**
 * The two parallel lists a pick list is saved as. Kept as two lists of plain
 * values, the parity list in the shape it had before plates, so an app from
 * before several plates still reads the parities it knows.
 */
export function persistRoundPicks(picks: readonly RoundPick[]): {
  quadrants: (EchoQuadrant | null)[];
  plates: (number | null)[];
} {
  return {
    quadrants: picks.map((p) => p.quadrant),
    plates: picks.map((p) => p.plate),
  };
}

/**
 * The one place stored round picks are read (workspace restore, autosave
 * rehydration, the store setter), in the manner of `clampMaxPrimers`.
 *
 * `rawQuadrants` is the stored parity list and `rawPlates` the plate list
 * beside it. A file from before several plates has no plate list: its two
 * rounds were both on plate 1, so both read as plate 1. A missing parity list
 * is a file from before rounds and reads as no picks at all. An entry that is
 * not a current parity name or a positive integer plate becomes null, which
 * asks the operator again rather than guessing. A later round repeating an
 * earlier round's plate and parity loses its parity for the same reason: two
 * rounds on one parity of one plate would dispense onto primers already there.
 */
export function normalizeRoundPicks(rawQuadrants: unknown, rawPlates: unknown): RoundPicks {
  if (!Array.isArray(rawQuadrants)) return [];
  const legacy = !Array.isArray(rawPlates);
  const plates: unknown[] = legacy ? [1, 1] : (rawPlates as unknown[]);
  const length = legacy
    ? Math.max(2, rawQuadrants.length)
    : Math.max(rawQuadrants.length, plates.length);
  const quadrant = (v: unknown): EchoQuadrant | null =>
    typeof v === "string" && (ECHO_QUADRANTS as readonly string[]).includes(v)
      ? (v as EchoQuadrant)
      : null;
  const plate = (v: unknown): number | null =>
    typeof v === "number" && Number.isInteger(v) && v >= 1 ? v : null;
  const out: RoundPicks = [];
  for (let k = 0; k < length; k++) {
    const next: RoundPick = { plate: plate(plates[k]), quadrant: quadrant(rawQuadrants[k]) };
    if (
      next.plate !== null &&
      next.quadrant !== null &&
      out.some((p) => p.plate === next.plate && p.quadrant === next.quadrant)
    ) {
      next.quadrant = null;
    }
    out.push(next);
  }
  return out;
}
