/**
 * replicateConcordance.ts, "do the replicates of one well agree?", as a pure
 * function over an analyze response.
 *
 * The axis this reads is the one the pipeline itself runs on. A run's native
 * barcodes are REPLICATES of one plate, not separate plates: the layout is one
 * per run and applies to every native barcode, and
 * `kuma_core/mame/pipeline.py` groups records by `native_barcode` before
 * `pick_best_replicate` picks one of them. The well is fixed by the custom
 * barcode pair (R = row, F = column), so `custom_barcode` is the same well on
 * every plate copy and is therefore the pivot key here.
 *
 * Keying on `mutant_id` instead would be wrong twice over: a well whose copies
 * were assigned different variant ids is exactly the case worth flagging, and
 * two wells carrying the same variant would collapse into one row.
 *
 * Nothing here re-derives a well coordinate. `custom_barcode` is carried
 * through verbatim, and ordering defers to `wellSortKey` / `nbOrderKey`
 * (lib/mame/nbLabel.ts), which mirror the Python addressing rule.
 *
 * Three flags, and one of them can be undecidable:
 *
 *   verdict_disagreement, the plate copies of this well were not called the
 *     same. `pick_best_replicate` will still pick one, and the picked verdict
 *     alone never says the others differed.
 *   depth_imbalance, one copy carries far fewer reads than another, so a
 *     disagreement between them is as likely to be sequencing depth as biology.
 *   missing_replicate, a plate that was scored has no record for this well at
 *     all. Only decidable when the caller can state which plates the run was
 *     supposed to cover (`expectedPlates`); a consensus-directory run has no
 *     such statement, and guessing it from the records present would make the
 *     flag structurally unable to fire. Undecidable is reported as `null`, not
 *     as `false`.
 */

import type { VerdictClass, VerdictRecord } from "@/types/mame/models";
import { nbOrderKey, wellSortKey } from "@/lib/mame/nbLabel";

/**
 * A replicate is called depth-imbalanced when the shallowest copy carries less
 * than this fraction of the deepest one.
 *
 * A ratio, not an absolute read floor, because the question this flag answers
 * is comparative: "can these copies be compared with each other?" An absolute
 * floor answers a different question ("is this copy deep enough to call at
 * all?"), and the per-well depth columns and LOWDEPTH verdicts already answer
 * that one. The two rules disagree in both directions, which is why picking one
 * matters: 10 vs 40 reads is proportionate but shallow (a floor flags it, this
 * does not), and 100 vs 1000 reads is deep but lopsided (this flags it, a floor
 * does not).
 *
 * Strict `<`: a copy at exactly a fifth of its sibling is the boundary and is
 * not flagged.
 */
export const DEPTH_IMBALANCE_MIN_RATIO = 0.2;

/** One plate copy of one well. */
export interface ReplicateCell {
  /** native_barcode, i.e. the sort_barcode name the pipeline grouped on. */
  plate: string;
  verdict: VerdictClass;
  mutantId: string;
  readCount: number | null;
  alignedReads: number | null;
}

export interface WellConcordance {
  /** custom_barcode, verbatim. */
  well: string;
  /** Plate copies found for this well, ordered by plate. */
  cells: ReplicateCell[];
  presentPlates: string[];
  /** Empty when `missingReplicate` is null (nothing to be missing from). */
  missingPlates: string[];
  verdictDisagreement: boolean;
  depthImbalance: boolean;
  /** min/max read count across the copies that reported one, else null. */
  depthRatio: number | null;
  /** null = not decidable for this run. */
  missingReplicate: boolean | null;
}

export interface ReplicateConcordance {
  /** The plates the flags are measured against, ordered. */
  plates: string[];
  /** false = derived from the records present, so missingReplicate is null. */
  platesKnown: boolean;
  wells: WellConcordance[];
  byWell: Map<string, WellConcordance>;
  flaggedWells: number;
}

export interface ReplicateConcordanceOptions {
  depthImbalanceMinRatio?: number;
}

function orderPlates(plates: Iterable<string>): string[] {
  return Array.from(new Set(plates)).sort(
    (a, b) => nbOrderKey(a) - nbOrderKey(b) || a.localeCompare(b),
  );
}

function hasFlag(well: WellConcordance): boolean {
  return (
    well.verdictDisagreement || well.depthImbalance || well.missingReplicate === true
  );
}

/**
 * @param expectedPlates the plates this run scored, as native_barcode
 *   (`sort_barcodeNN`) names. Pass null when the run cannot state them; the
 *   `missing_replicate` flag is then reported as undecidable.
 */
export function computeReplicateConcordance(
  verdicts: readonly VerdictRecord[],
  expectedPlates: readonly string[] | null,
  options: ReplicateConcordanceOptions = {},
): ReplicateConcordance {
  const minRatio = options.depthImbalanceMinRatio ?? DEPTH_IMBALANCE_MIN_RATIO;

  const observed = orderPlates(verdicts.map((v) => v.native_barcode));
  // One copy is not a replicate set: a run with a single plate has nothing for
  // a well to be missing from, so the flag stays undecidable there too.
  const platesKnown = expectedPlates !== null && expectedPlates.length >= 2;
  const plates = platesKnown ? orderPlates(expectedPlates) : observed;

  const grouped = new Map<string, ReplicateCell[]>();
  for (const record of verdicts) {
    const cells = grouped.get(record.custom_barcode);
    const cell: ReplicateCell = {
      plate: record.native_barcode,
      verdict: record.verdict,
      mutantId: record.mutant_id,
      readCount: record.read_count,
      alignedReads: record.n_aligned_reads,
    };
    if (cells) cells.push(cell);
    else grouped.set(record.custom_barcode, [cell]);
  }

  const wells: WellConcordance[] = [];
  for (const [well, rawCells] of grouped) {
    const cells = [...rawCells].sort(
      (a, b) => nbOrderKey(a.plate) - nbOrderKey(b.plate) || a.plate.localeCompare(b.plate),
    );
    const presentPlates = orderPlates(cells.map((c) => c.plate));

    const verdictDisagreement =
      cells.length >= 2 && new Set(cells.map((c) => c.verdict)).size > 1;

    // Copies that reported no read count (a consensus directory need not carry
    // one) are left out rather than read as zero: an absent measurement must
    // not manufacture an imbalance.
    const depths = cells
      .map((c) => c.readCount)
      .filter((n): n is number => n !== null && Number.isFinite(n));
    let depthRatio: number | null = null;
    if (depths.length >= 2) {
      const max = Math.max(...depths);
      const min = Math.min(...depths);
      if (max > 0) depthRatio = min / max;
    }
    const depthImbalance = depthRatio !== null && depthRatio < minRatio;

    const missingPlates = platesKnown
      ? plates.filter((plate) => !presentPlates.includes(plate))
      : [];

    wells.push({
      well,
      cells,
      presentPlates,
      missingPlates,
      verdictDisagreement,
      depthImbalance,
      depthRatio,
      missingReplicate: platesKnown ? missingPlates.length > 0 : null,
    });
  }

  wells.sort(
    (a, b) =>
      wellSortKey(a.well)[0] - wellSortKey(b.well)[0] ||
      wellSortKey(a.well)[1] - wellSortKey(b.well)[1] ||
      a.well.localeCompare(b.well),
  );

  return {
    plates,
    platesKnown,
    wells,
    byWell: new Map(wells.map((w) => [w.well, w])),
    flaggedWells: wells.filter(hasFlag).length,
  };
}

/** True when this well carries at least one decided flag. */
export function isFlagged(well: WellConcordance | undefined): boolean {
  return well !== undefined && hasFlag(well);
}
