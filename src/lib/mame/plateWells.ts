import type { WellEntry } from "@/types/mame/models";

/**
 * Collapse to one record per well position.
 *
 * `wells` carries one entry per (well × replicate native barcode), so a plain
 * Map keyed by well position keeps only the LAST replicate — making the whole
 * plate show a single native barcode in combinatorial-sort runs. Prefer the
 * selected (winning) replicate; when no record at a position is selected, keep
 * the last-seen one (unchanged behaviour for single-replicate plates).
 */
export function collapseWells(wells: readonly WellEntry[]): WellEntry[] {
  const map = new Map<string, WellEntry>();
  for (const w of wells) {
    const existing = map.get(w.well);
    if (existing?.selected && !w.selected) continue;
    map.set(w.well, w);
  }
  return [...map.values()];
}
