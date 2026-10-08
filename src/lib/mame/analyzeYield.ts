/**
 * analyzeYield, narrow the demux yield out of an analyze response.
 *
 * The analyze handler only attaches the yield keys on the raw-run path;
 * consensus-dir runs omit all of them because that path never demuxes. Keep
 * that distinction intact so the zero-result explanation shows a count only
 * when the backend reported one, and never turns a missing count into a 0
 * (which would read as "every read was rejected", the opposite of "this mode
 * never counted"). Returns null when the response carried none of the fields.
 *
 * The fields copied here are the contract with `AnalyzeYield` and, through it,
 * with the response keys the handler emits. A counter added on the Python side
 * but not copied here is dropped before it reaches EmptyAnalysisNotice.
 *
 * `contamination` does NOT belong here even though it is raw-run-only for the
 * same reason. This narrowing exists to feed one widget a set of scalar counts,
 * and the stray-read report is neither scalar nor about yield: it is a set of
 * per-signal records with their own availability, carried on its own store
 * field (`contamination`) and rendered by its own panel. Folding it in would
 * make `AnalyzeYield` two things at once, and the zero-result notice would have
 * to decide what to do with a nested object it has nothing to say about.
 */
import type { AnalyzeYield } from "@/types/mame/models";

/**
 * The drop-reason counters, copied by the same present-or-absent rule as the
 * five scalars above. Listed once here so adding one to `AnalyzeYield` and
 * forgetting it here is a single edit to notice rather than a silent drop.
 */
const DROP_REASON_KEYS = [
  "drop_short_window_read_5p",
  "drop_short_window_read_3p",
  "drop_no_barcode_f",
  "drop_no_barcode_r",
  "drop_ambiguous_tie_f",
  "drop_ambiguous_tie_r",
  "drop_both_axes",
] as const satisfies readonly (keyof AnalyzeYield)[];

export function pickAnalyzeYield(result: AnalyzeYield): AnalyzeYield | null {
  const { assigned_reads, wells_with_reads, total_reads, passed_mapq, passed_coverage } = result;
  const picked: AnalyzeYield = {};
  if (assigned_reads !== undefined) picked.assigned_reads = assigned_reads;
  if (wells_with_reads !== undefined) picked.wells_with_reads = wells_with_reads;
  if (total_reads !== undefined) picked.total_reads = total_reads;
  if (passed_mapq !== undefined) picked.passed_mapq = passed_mapq;
  if (passed_coverage !== undefined) picked.passed_coverage = passed_coverage;
  for (const key of DROP_REASON_KEYS) {
    const value = result[key];
    if (value !== undefined) picked[key] = value;
  }
  return Object.keys(picked).length > 0 ? picked : null;
}
