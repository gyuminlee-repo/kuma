/**
 * analyzeYield, narrow the demux yield out of an analyze response.
 *
 * The analyze handler only attaches `assigned_reads` / `wells_with_reads` on the
 * raw-run path; consensus-dir runs omit both keys. Keep that distinction intact
 * so the zero-result explanation shows a count only when the backend reported
 * one. Returns null when the response carried neither field.
 */
import type { AnalyzeYield } from "@/types/mame/models";

export function pickAnalyzeYield(result: AnalyzeYield): AnalyzeYield | null {
  const { assigned_reads, wells_with_reads } = result;
  if (assigned_reads === undefined && wells_with_reads === undefined) return null;
  const picked: AnalyzeYield = {};
  if (assigned_reads !== undefined) picked.assigned_reads = assigned_reads;
  if (wells_with_reads !== undefined) picked.wells_with_reads = wells_with_reads;
  return picked;
}
