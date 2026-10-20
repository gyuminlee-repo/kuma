import type { WellEntry } from "@/types/mame/models";
import { nbOrderKey } from "@/lib/mame/nbLabel";

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

/** Every copy of every well position, ordered by plate label (NB07, NB08, ...). */
export function copiesByWell(wells: readonly WellEntry[]): Map<string, WellEntry[]> {
  const map = new Map<string, WellEntry[]>();
  for (const w of wells) {
    const list = map.get(w.well);
    if (list) list.push(w);
    else map.set(w.well, [w]);
  }
  for (const list of map.values()) {
    list.sort(
      (a, b) =>
        nbOrderKey(a.native_barcode) - nbOrderKey(b.native_barcode) ||
        a.native_barcode.localeCompare(b.native_barcode),
    );
  }
  return map;
}

/** Distinct native barcodes present in the run, in plate order. */
export function plateBarcodes(wells: readonly WellEntry[]): string[] {
  return [...new Set(wells.map((w) => w.native_barcode).filter(Boolean))].sort(
    (a, b) => nbOrderKey(a) - nbOrderKey(b) || a.localeCompare(b),
  );
}
