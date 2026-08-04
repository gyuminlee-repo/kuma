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
 */
import type { AnalyzeYield } from "@/types/mame/models";

export function pickAnalyzeYield(result: AnalyzeYield): AnalyzeYield | null {
  const { assigned_reads, wells_with_reads, total_reads, passed_mapq, passed_coverage } = result;
  const picked: AnalyzeYield = {};
  if (assigned_reads !== undefined) picked.assigned_reads = assigned_reads;
  if (wells_with_reads !== undefined) picked.wells_with_reads = wells_with_reads;
  if (total_reads !== undefined) picked.total_reads = total_reads;
  if (passed_mapq !== undefined) picked.passed_mapq = passed_mapq;
  if (passed_coverage !== undefined) picked.passed_coverage = passed_coverage;
  return Object.keys(picked).length > 0 ? picked : null;
}
